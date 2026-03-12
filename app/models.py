"""Commerce models — products, cart schemas, and orders."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class OrderStatus(str, Enum):
    PLACED = "placed"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, nullable=False, index=True)
    name = Column(String(160), nullable=False, index=True)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    stock_quantity = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, nullable=True, index=True)
    customer_name = Column(String(160), nullable=False, default="Guest Customer")
    status = Column(String(40), nullable=False, default=OrderStatus.PLACED.value)
    total_amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="INR")
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    product_name = Column(String(160), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")


class ProductCreate(BaseModel):
    business_id: int
    name: str = Field(min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=400)
    price: float = Field(ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=400)
    price: Optional[float] = Field(default=None, ge=0)
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class ProductResponse(BaseModel):
    id: int
    business_id: int
    name: str
    description: Optional[str]
    price: float
    stock_quantity: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CartItemAdd(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=50)


class CartItemResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    line_total: float


class CartResponse(BaseModel):
    items: list[CartItemResponse] = Field(default_factory=list)
    total_amount: float = 0
    currency: str = "INR"


class OrderCreate(BaseModel):
    customer_name: str = Field(default="Guest Customer", min_length=2, max_length=160)


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    line_total: float

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    customer_id: Optional[int]
    customer_name: str
    status: str
    total_amount: float
    currency: str
    created_at: datetime
    items: list[OrderItemResponse]

    class Config:
        from_attributes = True
