import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, Product, Category, Banner, Offer, Coupon, DeliveryArea, Cart, CartItem, Order, Notification

class ObjectIdStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        try:
            return str(ObjectId(str(v)))
        except Exception:
            raise ValueError("Invalid ObjectId")

app = FastAPI(title="The Herbal Chicken API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"name": "The Herbal Chicken", "status": "ok"}

# Public endpoints

@app.get("/api/categories")
def list_categories():
    return get_documents("category")

@app.get("/api/products")
async def list_products(category: Optional[str] = None, q: Optional[str] = None):
    filt = {}
    if category:
        filt["category"] = category
    if q:
        filt["$or"] = [{"title": {"$regex": q, "$options": "i"}}, {"description": {"$regex": q, "$options": "i"}}]
    return get_documents("product", filt)

@app.get("/api/banners")
def list_banners():
    return get_documents("banner", {"active": True})

@app.get("/api/offers")
def list_offers():
    return get_documents("offer", {"active": True})

@app.get("/api/areas")
def list_areas():
    return get_documents("deliveryarea", {"active": True})

# Auth (simplified email+mobile registration/login)
class AuthPayload(BaseModel):
    name: Optional[str] = None
    email: str
    mobile: str

@app.post("/api/auth/register")
def register(payload: AuthPayload):
    existing = db["user"].find_one({"$or": [{"email": payload.email}, {"mobile": payload.mobile}]})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    user = User(name=payload.name or "", email=payload.email, mobile=payload.mobile)
    uid = create_document("user", user)
    return {"user_id": uid}

@app.post("/api/auth/login")
def login(payload: AuthPayload):
    user = db["user"].find_one({"$or": [{"email": payload.email}, {"mobile": payload.mobile}]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": str(user.get("_id")), "name": user.get("name"), "email": user.get("email"), "mobile": user.get("mobile")}

# Cart endpoints (simple server-side cart per user)
@app.get("/api/cart/{user_id}")
def get_cart(user_id: str):
    cart = db["cart"].find_one({"user_id": user_id})
    if not cart:
        cart_doc = Cart(user_id=user_id)
        create_document("cart", cart_doc)
        cart = db["cart"].find_one({"user_id": user_id})
    cart["_id"] = str(cart["_id"])  # jsonify ObjectId
    return cart

class CartUpdate(BaseModel):
    product_id: str
    quantity: int

@app.post("/api/cart/{user_id}/add")
def add_to_cart(user_id: str, upd: CartUpdate):
    prod = db["product"].find_one({"_id": ObjectId(upd.product_id)})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    cart = db["cart"].find_one({"user_id": user_id})
    if not cart:
        cart = {"user_id": user_id, "items": []}
    items = cart.get("items", [])
    found = False
    for it in items:
        if it["product_id"] == upd.product_id:
            it["quantity"] = upd.quantity
            found = True
            break
    if not found:
        items.append({
            "product_id": upd.product_id,
            "title": prod.get("title"),
            "price": float(prod.get("price", 0)),
            "quantity": upd.quantity,
            "image_url": prod.get("image_url")
        })
    db["cart"].update_one({"user_id": user_id}, {"$set": {"items": items}}, upsert=True)
    return {"ok": True}

@app.post("/api/cart/{user_id}/remove")
def remove_from_cart(user_id: str, upd: CartUpdate):
    cart = db["cart"].find_one({"user_id": user_id})
    if not cart:
        return {"ok": True}
    items = [it for it in cart.get("items", []) if it["product_id"] != upd.product_id]
    db["cart"].update_one({"user_id": user_id}, {"$set": {"items": items}})
    return {"ok": True}

class ApplyCoupon(BaseModel):
    code: str

@app.post("/api/cart/{user_id}/apply-coupon")
def apply_coupon(user_id: str, payload: ApplyCoupon):
    coupon = db["coupon"].find_one({"code": payload.code, "active": True})
    if not coupon:
        raise HTTPException(status_code=404, detail="Invalid coupon")
    db["cart"].update_one({"user_id": user_id}, {"$set": {"coupon_code": payload.code}})
    return {"ok": True}

# Checkout and orders
class CheckoutPayload(BaseModel):
    address: dict
    area_pincode: str
    payment_method: str  # COD or ONLINE

@app.post("/api/checkout/{user_id}")
def checkout(user_id: str, data: CheckoutPayload):
    cart = db["cart"].find_one({"user_id": user_id})
    if not cart or not cart.get("items"):
        raise HTTPException(status_code=400, detail="Cart is empty")

    subtotal = sum([it["price"] * it["quantity"] for it in cart.get("items", [])])
    discount = 0.0
    if cart.get("coupon_code"):
        cpn = db["coupon"].find_one({"code": cart.get("coupon_code"), "active": True})
        if cpn:
            if cpn.get("discount_type") == "percent":
                discount = min(subtotal * float(cpn.get("value", 0)) / 100.0, float(cpn.get("max_discount", subtotal)))
            else:
                discount = min(float(cpn.get("value", 0)), float(cpn.get("max_discount", subtotal)))
    final_amount = max(0.0, subtotal - discount)

    payment = {
        "method": "COD" if data.payment_method.upper() == "COD" else "ONLINE",
        "provider": None if data.payment_method.upper() == "COD" else "razorpay",
        "status": "pending" if data.payment_method.upper() == "ONLINE" else "paid"
    }

    order_doc = {
        "user_id": user_id,
        "items": cart.get("items", []),
        "total_amount": round(subtotal, 2),
        "discount_amount": round(discount, 2),
        "final_amount": round(final_amount, 2),
        "address": data.address,
        "area_pincode": data.area_pincode,
        "payment": payment,
        "status": "placed",
        "tracking_code": str(ObjectId())[:8].upper()
    }
    oid = create_document("order", order_doc)
    db["cart"].update_one({"user_id": user_id}, {"$set": {"items": [], "coupon_code": None}})

    # create notification
    create_document("notification", {
        "user_id": user_id,
        "title": "Order Placed",
        "message": f"Your order #{oid} has been placed.",
        "type": "order",
        "read": False
    })

    return {"order_id": oid, "tracking_code": order_doc["tracking_code"], "payment": payment}

@app.get("/api/orders/{user_id}")
def list_orders(user_id: str):
    orders = list(db["order"].find({"user_id": user_id}).sort("created_at", -1))
    for o in orders:
        o["_id"] = str(o["_id"]) 
    return orders

@app.get("/api/track/{tracking_code}")
def track_order(tracking_code: str):
    order = db["order"].find_one({"tracking_code": tracking_code})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order["_id"] = str(order["_id"]) 
    return order

# Admin endpoints (basic CRUD)

@app.post("/api/admin/category")
def admin_create_category(cat: Category):
    cid = create_document("category", cat)
    return {"id": cid}

@app.post("/api/admin/product")
def admin_create_product(p: Product):
    pid = create_document("product", p)
    return {"id": pid}

@app.post("/api/admin/banner")
def admin_create_banner(b: Banner):
    bid = create_document("banner", b)
    return {"id": bid}

@app.post("/api/admin/offer")
def admin_create_offer(o: Offer):
    oid = create_document("offer", o)
    return {"id": oid}

@app.post("/api/admin/coupon")
def admin_create_coupon(c: Coupon):
    cid = create_document("coupon", c)
    return {"id": cid}

@app.get("/api/notifications/{user_id}")
def get_notifications(user_id: str):
    notes = get_documents("notification", {"user_id": user_id})
    return notes

@app.get("/api/schema")
def get_schema():
    # Let admin tools read available schemas
    from inspect import getmembers, isclass
    import schemas as schema_module
    classes = {
        name: cls.model_json_schema()
        for name, cls in getmembers(schema_module)
        if isclass(cls) and issubclass(cls, BaseModel)
    }
    return classes

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
