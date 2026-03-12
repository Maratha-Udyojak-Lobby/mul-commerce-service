from datetime import datetime
import os
from typing import Optional

import jwt
from fastapi import FastAPI, Depends, HTTPException, Query, Header, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.cart_store import CartStore, get_cart_store
from app.database import get_db, init_db
from app.models import (
    Product,
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    CartItemAdd,
    CartItemResponse,
    CartResponse,
    Order,
    OrderItem,
    OrderCreate,
    OrderResponse,
    OrderStatus,
)

init_db()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "mul-super-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

app = FastAPI(
    title="MUL Commerce Service",
    version="1.0.0",
    description="Products, inventory, cart, and orders",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _decode_user_id(authorization: Optional[str]) -> Optional[int]:
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        payload = jwt.decode(parts[1], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return int(payload.get("sub", 0)) or None
    except jwt.InvalidTokenError:
        return None


def _require_user_id(authorization: Optional[str]) -> int:
    user_id = _decode_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user_id


def _resolve_cart_id(authorization: Optional[str], x_cart_id: Optional[str]) -> tuple[str, Optional[int]]:
    user_id = _decode_user_id(authorization)
    if user_id:
        return f"user:{user_id}", user_id

    if x_cart_id and x_cart_id.strip():
        return f"anon:{x_cart_id.strip()}", None

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (or provide X-Cart-Id for guest cart)",
    )


def _fetch_products_map(db: Session, product_ids: list[int]) -> dict[int, Product]:
    if not product_ids:
        return {}

    products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    return {product.id: product for product in products}


def _build_cart_response(
    quantities: dict[int, int],
    products_map: dict[int, Product],
) -> CartResponse:
    items: list[CartItemResponse] = []
    total_amount = 0.0

    for product_id, quantity in quantities.items():
        if quantity <= 0:
            continue

        product = products_map.get(product_id)
        if not product or not product.is_active:
            continue

        line_total = round(product.price * quantity, 2)
        total_amount += line_total
        items.append(
            CartItemResponse(
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.price,
                line_total=line_total,
            )
        )

    return CartResponse(items=items, total_amount=round(total_amount, 2), currency="INR")


def _seed_products(db: Session) -> None:
    if db.query(Product).count() > 0:
        return

    now = datetime.utcnow()
    products = [
        Product(
            business_id=1,
            name="Organic Turmeric Powder",
            description="200g pouch",
            price=149,
            stock_quantity=120,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        Product(
            business_id=1,
            name="Groundnut Oil",
            description="1 litre",
            price=220,
            stock_quantity=80,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        Product(
            business_id=1,
            name="Millet Mix",
            description="500g",
            price=180,
            stock_quantity=60,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
    ]

    db.add_all(products)
    db.commit()


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    db = next(get_db())
    try:
        _seed_products(db)
    finally:
        db.close()


@app.get("/", summary="Commerce Service Root")
async def root() -> dict:
    return {"message": "MUL Commerce Service is running"}


@app.get("/health", summary="Health Check")
async def health() -> dict:
    return {"status": "ok", "service": "commerce-service"}


@app.get("/api/v1/products", summary="List Products", response_model=list[ProductResponse])
async def list_products(
    business_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, min_length=2),
    db: Session = Depends(get_db),
) -> list[ProductResponse]:
    query = db.query(Product).filter(Product.is_active == True)

    if business_id is not None:
        query = query.filter(Product.business_id == business_id)

    if search:
        search_key = f"%{search.strip()}%"
        query = query.filter(
            or_(Product.name.ilike(search_key), Product.description.ilike(search_key))
        )

    return query.order_by(Product.name.asc()).all()


@app.get("/api/v1/products/{product_id}", summary="Get Product", response_model=ProductResponse)
async def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductResponse:
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@app.post("/api/v1/products", summary="Create Product", response_model=ProductResponse, status_code=201)
async def create_product(
    data: ProductCreate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> ProductResponse:
    _require_user_id(authorization)
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.patch("/api/v1/products/{product_id}", summary="Update Product", response_model=ProductResponse)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> ProductResponse:
    _require_user_id(authorization)
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product


@app.post("/api/v1/cart/items", summary="Add Item to Cart", response_model=CartResponse)
async def add_cart_item(
    data: CartItemAdd,
    authorization: Optional[str] = Header(None),
    x_cart_id: Optional[str] = Header(None, alias="X-Cart-Id"),
    db: Session = Depends(get_db),
    cart_store: CartStore = Depends(get_cart_store),
) -> CartResponse:
    cart_id, _ = _resolve_cart_id(authorization, x_cart_id)

    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if not product.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product is not available")

    quantities = cart_store.get_quantities(cart_id)
    current_quantity = quantities.get(data.product_id, 0)
    requested_quantity = current_quantity + data.quantity

    if requested_quantity > product.stock_quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient inventory for requested quantity",
        )

    quantities[data.product_id] = requested_quantity
    cart_store.set_quantities(cart_id, quantities)
    products_map = _fetch_products_map(db, list(quantities.keys()))
    return _build_cart_response(quantities, products_map)


@app.get("/api/v1/cart", summary="Get Cart", response_model=CartResponse)
async def get_cart(
    authorization: Optional[str] = Header(None),
    x_cart_id: Optional[str] = Header(None, alias="X-Cart-Id"),
    db: Session = Depends(get_db),
    cart_store: CartStore = Depends(get_cart_store),
) -> CartResponse:
    cart_id, _ = _resolve_cart_id(authorization, x_cart_id)
    quantities = cart_store.get_quantities(cart_id)
    products_map = _fetch_products_map(db, list(quantities.keys()))
    return _build_cart_response(quantities, products_map)


@app.delete("/api/v1/cart/items/{product_id}", summary="Remove Item from Cart", response_model=CartResponse)
async def remove_cart_item(
    product_id: int,
    authorization: Optional[str] = Header(None),
    x_cart_id: Optional[str] = Header(None, alias="X-Cart-Id"),
    db: Session = Depends(get_db),
    cart_store: CartStore = Depends(get_cart_store),
) -> CartResponse:
    cart_id, _ = _resolve_cart_id(authorization, x_cart_id)
    quantities = cart_store.get_quantities(cart_id)
    quantities.pop(product_id, None)
    cart_store.set_quantities(cart_id, quantities)
    products_map = _fetch_products_map(db, list(quantities.keys()))
    return _build_cart_response(quantities, products_map)


@app.post("/api/v1/orders", summary="Create Order", response_model=OrderResponse, status_code=201)
async def create_order(
    payload: Optional[OrderCreate] = None,
    authorization: Optional[str] = Header(None),
    x_cart_id: Optional[str] = Header(None, alias="X-Cart-Id"),
    db: Session = Depends(get_db),
    cart_store: CartStore = Depends(get_cart_store),
) -> OrderResponse:
    cart_id, user_id = _resolve_cart_id(authorization, x_cart_id)
    quantities = cart_store.get_quantities(cart_id)
    products_map = _fetch_products_map(db, list(quantities.keys()))
    cart = _build_cart_response(quantities, products_map)

    if not cart.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    # Validate inventory again at checkout
    for item in cart.items:
        product = products_map.get(item.product_id)
        if not product or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more products are unavailable",
            )
        if product.stock_quantity < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient inventory during checkout",
            )

    order_payload = payload or OrderCreate()
    order = Order(
        customer_id=user_id,
        customer_name=order_payload.customer_name,
        status=OrderStatus.PLACED.value,
        total_amount=cart.total_amount,
        currency=cart.currency,
    )
    db.add(order)
    db.flush()

    for item in cart.items:
        product = products_map[item.product_id]
        product.stock_quantity -= item.quantity

        order_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        db.add(order_item)

    db.commit()
    cart_store.clear(cart_id)

    created = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.id == order.id)
        .first()
    )
    return created


@app.get("/api/v1/orders/{order_id}", summary="Get Order", response_model=OrderResponse)
async def get_order(order_id: int, db: Session = Depends(get_db)) -> OrderResponse:
    order = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order
