"""
Database Schemas for The Herbal Chicken

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercased class name (e.g., User -> "user").
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, EmailStr

# Core domain schemas

class Address(BaseModel):
    label: str = Field(..., description="e.g., Home, Work")
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    pincode: str
    coordinates: Optional[tuple[float, float]] = Field(None, description="lat, lng")

class User(BaseModel):
    name: str
    email: EmailStr
    mobile: str = Field(..., min_length=7, max_length=15)
    avatar_url: Optional[str] = None
    addresses: List[Address] = []
    referral_code: Optional[str] = None
    referred_by: Optional[str] = None
    is_admin: bool = False
    is_active: bool = True

class Category(BaseModel):
    name: Literal["Chicken", "Mutton", "Fish", "Eggs"]
    slug: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    active: bool = True

class Product(BaseModel):
    title: str
    sku: Optional[str] = None
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    mrp: Optional[float] = Field(None, ge=0)
    unit: Literal["kg", "g", "piece", "dozen"] = "kg"
    weight: Optional[float] = None
    category: Literal["Chicken", "Mutton", "Fish", "Eggs"]
    image_url: str
    in_stock: bool = True
    tags: List[str] = []

class Banner(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    image_url: str
    aspect_ratio: str = Field("16:9", description="Expected 16:9 ratio")
    active: bool = True

class Offer(BaseModel):
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    active: bool = True

class Coupon(BaseModel):
    code: str
    discount_type: Literal["percent", "flat"]
    value: float = Field(..., ge=0)
    min_amount: float = 0
    max_discount: Optional[float] = None
    active: bool = True

class DeliveryArea(BaseModel):
    name: str
    pincode: str
    city: Optional[str] = None
    active: bool = True

class CartItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int = Field(1, ge=1)
    image_url: Optional[str] = None

class Cart(BaseModel):
    user_id: str
    items: List[CartItem] = []
    area_pincode: Optional[str] = None
    coupon_code: Optional[str] = None

class PaymentInfo(BaseModel):
    method: Literal["COD", "ONLINE"]
    provider: Optional[Literal["razorpay", "stripe"]] = None
    transaction_id: Optional[str] = None
    status: Literal["pending", "paid", "failed"] = "pending"

class Order(BaseModel):
    user_id: str
    items: List[CartItem]
    total_amount: float
    discount_amount: float = 0
    final_amount: float
    address: Address
    area_pincode: str
    payment: PaymentInfo
    status: Literal["placed", "confirmed", "preparing", "out_for_delivery", "delivered", "cancelled"] = "placed"
    tracking_code: Optional[str] = None

class Referral(BaseModel):
    user_id: str
    code: str
    referred_user_id: Optional[str] = None

class Notification(BaseModel):
    user_id: str
    title: str
    message: str
    type: Literal["order", "promotion", "system"] = "order"
    read: bool = False
