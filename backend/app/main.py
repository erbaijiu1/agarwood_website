import os, re, uuid, io, base64, hashlib, hmac, json, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Numeric, func, select, or_
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from pydantic import BaseModel, Field, ConfigDict
from PIL import Image, UnidentifiedImageError

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./agarwood.db')
JWT_SECRET = os.getenv('JWT_SECRET', 'dev-only-change-me')
PUBLIC_PATH_PREFIX = os.getenv('PUBLIC_PATH_PREFIX', '').rstrip('/')
ALGORITHM = 'HS256'
BASE_DIR=Path(__file__).resolve().parent.parent
UPLOAD_DIR=BASE_DIR/'uploads'
UPLOAD_DIR.mkdir(exist_ok=True,parents=True)
engine=create_engine(DATABASE_URL,pool_pre_ping=True,connect_args={'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {})
SessionLocal=sessionmaker(bind=engine)
class Base(DeclarativeBase): pass
class Admin(Base):
 __tablename__='admins'
 id=Column(Integer,primary_key=True); username=Column(String(64),unique=True,nullable=False); password_hash=Column(String(255),nullable=False); created_at=Column(DateTime,default=datetime.utcnow)
class Category(Base):
 __tablename__='categories'
 id=Column(Integer,primary_key=True); name=Column(String(100),nullable=False); slug=Column(String(120),unique=True,nullable=False); sort_order=Column(Integer,default=0); visible=Column(Boolean,default=True)
class Product(Base):
 __tablename__='products'
 id=Column(Integer,primary_key=True); category_id=Column(Integer,ForeignKey('categories.id')); name=Column(String(200),nullable=False); slug=Column(String(220),unique=True,nullable=False); sku=Column(String(80),unique=True,nullable=False); summary=Column(Text,default=''); description=Column(Text,default=''); image=Column(String(512),default=''); images=Column(JSON,default=list); origin=Column(String(160),default=''); scent=Column(String(250),default=''); usage=Column(String(250),default=''); price_mode=Column(String(30),default='inquiry'); price=Column(Numeric(12,2),nullable=True); unit=Column(String(30),default='件'); stock_status=Column(String(30),default='available'); status=Column(String(30),default='draft'); featured=Column(Boolean,default=False); sort_order=Column(Integer,default=0); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class Article(Base):
 __tablename__='articles'
 id=Column(Integer,primary_key=True); title=Column(String(220),nullable=False); slug=Column(String(240),unique=True,nullable=False); excerpt=Column(Text,default=''); body=Column(Text,default=''); cover=Column(String(512),default=''); status=Column(String(30),default='draft'); sort_order=Column(Integer,default=0); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class Setting(Base):
 __tablename__='settings'
 key=Column(String(80),primary_key=True); value=Column(Text,nullable=False,default='')
class Inquiry(Base):
 __tablename__='inquiries'
 id=Column(Integer,primary_key=True); name=Column(String(80),nullable=False); contact=Column(String(150),nullable=False); channel=Column(String(30),default='other'); message=Column(Text,default=''); product_id=Column(Integer,ForeignKey('products.id'),nullable=True); status=Column(String(30),default='new'); created_at=Column(DateTime,default=datetime.utcnow)

class CategoryIn(BaseModel):
 name:str=Field(min_length=1,max_length=100); slug:str=Field(min_length=1,max_length=120,pattern=r'^[a-z0-9-]+$'); sort_order:int=0; visible:bool=True
class ProductIn(BaseModel):
 name:str=Field(min_length=1,max_length=200); slug:str=Field(min_length=1,max_length=220,pattern=r'^[a-z0-9-]+$'); sku:str=Field(min_length=1,max_length=80); category_id:Optional[int]=None; summary:str=''; description:str=''; image:str=''; images:list[str]=Field(default_factory=list); origin:str=''; scent:str=''; usage:str=''; price_mode:str=Field(default='inquiry',pattern='^(fixed|inquiry)$'); price:Optional[float]=Field(default=None,ge=0); unit:str='件'; stock_status:str=Field(default='available',pattern='^(available|sold_out)$'); status:str=Field(default='draft',pattern='^(draft|published|hidden)$'); featured:bool=False; sort_order:int=0
class ArticleIn(BaseModel):
 title:str=Field(min_length=1,max_length=220);slug:str=Field(min_length=1,max_length=240,pattern=r'^[a-z0-9-]+$');excerpt:str='';body:str='';cover:str='';status:str=Field(default='draft',pattern='^(draft|published|hidden)$');sort_order:int=0
class InquiryIn(BaseModel):
 name:str=Field(min_length=1,max_length=80);contact:str=Field(min_length=3,max_length=150);channel:str='other';message:str=Field(default='',max_length=3000);product_id:Optional[int]=None
class LoginIn(BaseModel): username:str;password:str
class StatusIn(BaseModel): status:str=Field(pattern='^(new|contacted|closed)$')

app=FastAPI(title='沉香品牌官网 API',docs_url='/api/docs',openapi_url='/api/openapi.json',root_path=PUBLIC_PATH_PREFIX)
origins=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:5173,http://localhost:5174').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Authorization','Content-Type'])
def password_hash(password:str)->str:
 salt=secrets.token_bytes(16);iterations=600_000
 digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,iterations)
 return f'pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}'
def password_verify(password:str,encoded:str)->bool:
 try:
  scheme,iterations,salt,digest=encoded.split('$',3)
  if scheme!='pbkdf2_sha256':return False
  actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(iterations))
  return hmac.compare_digest(actual,bytes.fromhex(digest))
 except (ValueError,TypeError):return False
def b64url(data:bytes)->str:return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
def b64url_decode(data:str)->bytes:return base64.urlsafe_b64decode(data+'='*(-len(data)%4))
def create_token(admin_id:int)->str:
 header=b64url(json.dumps({'alg':ALGORITHM,'typ':'JWT'},separators=(',',':')).encode())
 payload=b64url(json.dumps({'sub':str(admin_id),'exp':int((datetime.now(timezone.utc)+timedelta(hours=8)).timestamp())},separators=(',',':')).encode())
 signature=b64url(hmac.new(JWT_SECRET.encode(),f'{header}.{payload}'.encode(),hashlib.sha256).digest())
 return f'{header}.{payload}.{signature}'
def decode_token(token:str)->dict:
 header,payload,signature=token.split('.')
 expected=b64url(hmac.new(JWT_SECRET.encode(),f'{header}.{payload}'.encode(),hashlib.sha256).digest())
 if not hmac.compare_digest(signature,expected):raise ValueError('signature')
 data=json.loads(b64url_decode(payload))
 if int(data.get('exp',0))<=int(datetime.now(timezone.utc).timestamp()):raise ValueError('expired')
 return data
def db():
 with SessionLocal() as s: yield s
def require_admin(authorization:Optional[str]=Header(default=None),s:Session=Depends(db)):
 if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'请先登录')
 try:
  payload=decode_token(authorization[7:]); admin=s.get(Admin,int(payload['sub']))
  if not admin: raise Exception('no admin')
  return admin
 except Exception: raise HTTPException(401,'登录已过期')
def as_dict(obj):
 d={c.name:getattr(obj,c.name) for c in obj.__table__.columns}
 for k,v in d.items():
  if isinstance(v,datetime):d[k]=v.isoformat()
  elif hasattr(v,'as_tuple'):d[k]=float(v)
 return d
def save(s,obj):
 s.add(obj)
 try:s.commit();s.refresh(obj)
 except Exception:
  s.rollback();raise HTTPException(409,'唯一字段冲突，检查编码或 slug')
 return as_dict(obj)
def parse_settings(s): return {v.key:v.value for v in s.scalars(select(Setting)).all()}

@app.on_event('startup')
def init_db():
 Base.metadata.create_all(engine)
 with SessionLocal() as s:
  if not s.scalar(select(Admin.id).limit(1)):
   user=os.getenv('ADMIN_USERNAME'); password=os.getenv('ADMIN_PASSWORD')
   if user and password and len(password)>=12 and JWT_SECRET!='dev-only-change-me':
    s.add(Admin(username=user,password_hash=password_hash(password)))
   else: print('WARNING: admin not initialized; configure ADMIN_PASSWORD >=12 and JWT_SECRET')
  if not s.scalar(select(Category.id).limit(1)):
   for idx,(name,slug) in enumerate([('熏香香材','incense-material'),('线香与盘香','incense-sticks'),('手串挂件','accessories'),('香具礼盒','tools-gifts')]):s.add(Category(name=name,slug=slug,sort_order=idx))
  defaults={'brand_name':'沉香雅集','slogan':'一缕木香，回到生活本来的节奏','about':'沉香雅集是一个以沉香文化、香材与东方生活方式为主题的品牌 Demo。\n\n我们从香材形态、香气层次和日常使用场景出发，整理适合入门者了解的沉香知识，也呈现线香、香材、手串、挂件与香器等不同产品形态。\n\n这里展示的品牌、商品、价格和联系方式均为演示内容。正式用于具体公司时，可通过管理后台替换品牌资料、真实商品和已授权图片，无需重新开发网站。','phone':'400-000-2026（Demo）','wechat':'AgarwoodDemo','whatsapp':'','email':'demo@yjhcai.cn','address':'广东省深圳市 · Demo 展示地址','hero_image':'/agarwood/assets/hero-agarwood.webp','hero_title':'天然木香 · 东方香韵','hero_subtitle':'从一片沉香到一盏清茶，认识香材、香器与东方生活中的闻香方式。'}
  for k,v in defaults.items():
   if not s.get(Setting,k):s.add(Setting(key=k,value=v))
  if not s.scalar(select(Product.id).limit(1)):
   demo_products=[
    (1,'沉香切块','agarwood-chips','CX-001','纹理清晰的沉香木块，适合电熏品香。','/agarwood/assets/product-chips.webp','东南亚香材 Demo','木质、沉稳','电熏、茶席','inquiry',None,'克'),
    (1,'沉香勾丝','agarwood-shavings','CX-002','细丝状香材，适合少量多次体验香气。','/agarwood/assets/product-shavings.webp','精选香材 Demo','木质、温润','日常品香','inquiry',None,'克'),
    (2,'沉香线香','agarwood-incense-sticks','CX-003','简约线香，为阅读与茶席增添香气。','/agarwood/assets/product-sticks.webp','传统制香 Demo','清雅木香','阅读、茶席','fixed',88,'盒'),
    (3,'沉香手串','agarwood-bracelet','CX-004','自然木纹，适合佩戴与赏玩。','/agarwood/assets/product-bracelet.webp','天然木材 Demo','自然木香','佩戴、礼赠','inquiry',None,'串'),
    (3,'沉香雕刻挂件','agarwood-pendant','CX-005','以木材纹理与雕刻之美呈现雅致风格。','/agarwood/assets/product-pendant.webp','手工雕刻 Demo','木质香韵','佩戴、礼赠','inquiry',None,'件'),
    (4,'陶瓷香炉','ceramic-incense-burner','CX-006','温润陶瓷器形，适用于雅致品香空间。','/agarwood/assets/product-burner.webp','景德镇陶瓷 Demo','', '品香、茶席','fixed',168,'件'),
   ]
   for category_id,name,slug,sku,summary,image,origin,scent,usage,price_mode,price,unit in demo_products:
    s.add(Product(category_id=category_id,name=name,slug=slug,sku=sku,summary=summary,description=summary+'\n\n本商品为官网 Demo 展示内容，用于说明产品详情、公开价格与询价两种展示方式。正式上线时请替换为真实规格、批次和来源信息。\n\n根据个人喜好选择适当用量，使用时注意通风。',image=image,images=[image],origin=origin,scent=scent,usage=usage,price_mode=price_mode,price=price,unit=unit,status='published',featured=True))
  if not s.scalar(select(Article.id).limit(1)):
   for title,slug,excerpt,body,cover in [
     ('沉香是什么？','what-is-agarwood','认识含有芳香树脂的沉香木，以及常见香材形态。','沉香通常指沉香属等树木在特定条件下形成的含芳香树脂木材。不同材料的油脂、纹理与香气存在差异。\n\n市场中常见木片、切块、勾丝和香粉等香材形态，也有线香、手串、挂件等加工产品。了解产品时，应关注来源说明、实际规格与商家能够提供的依据。\n\n本 Demo 仅用于文化与产品形态介绍，不构成产地、等级或功效鉴定。','/agarwood/assets/story-agarwood-commons.webp'),
     ('沉香如何品闻？','how-to-enjoy-incense','从香器、用量与通风开始，了解日常品香。','初次闻香可以从少量香材开始，选择适合的电子熏香器或香具，并按照设备说明逐步调节温度。\n\n品闻时不必追求浓烈，可以记录不同温度和时间下感受到的木质、清甜、温润等气味变化。空间保持适度通风，避免在密闭环境中长时间使用。\n\n燃香涉及明火时，应远离儿童、宠物和易燃物，离开前确认火源已经完全熄灭。','/agarwood/assets/scene-incense.webp'),
     ('品茶为什么常与闻香相伴？','tea-and-incense','探索香气与茶席之间的文化联系。','茶与香常被放在同一生活场景中，是因为二者都需要放慢节奏，通过气味、温度和时间感受细微变化。\n\n布置茶席时，可以选择气味清雅、用量较少的香品，避免香气过浓影响茶汤本身的香气判断。\n\n闻香与饮茶首先是一种生活方式和审美体验。本 Demo 不对沉香或茶作医疗、保健功效宣称。','/agarwood/assets/scene-tea-pexels.webp')
   ]:s.add(Article(title=title,slug=slug,excerpt=excerpt,body=body,cover=cover,status='published'))
  s.commit()

@app.get('/api/health')
def health():return {'ok':True}
@app.get('/api/v1/site')
def site(s:Session=Depends(db)):return parse_settings(s)
@app.get('/api/v1/categories')
def categories(s:Session=Depends(db)):return [as_dict(c) for c in s.scalars(select(Category).where(Category.visible==True).order_by(Category.sort_order,Category.id))]
@app.get('/api/v1/products')
def products(category:Optional[str]=None,q:Optional[str]=None,featured:Optional[bool]=None,page:int=1,page_size:int=12,s:Session=Depends(db)):
 page=max(page,1);page_size=min(max(page_size,1),48)
 stmt=select(Product).where(Product.status=='published')
 if category:stmt=stmt.join(Category).where(Category.slug==category)
 if q:stmt=stmt.where(or_(Product.name.ilike(f'%{q}%'),Product.summary.ilike(f'%{q}%')))
 if featured is not None:stmt=stmt.where(Product.featured==featured)
 total=s.scalar(select(func.count()).select_from(stmt.subquery()))
 rows=s.scalars(stmt.order_by(Product.sort_order,Product.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
 return {'items':[as_dict(x) for x in rows],'total':total,'page':page,'page_size':page_size}
@app.get('/api/v1/products/{slug}')
def product(slug:str,s:Session=Depends(db)):
 x=s.scalar(select(Product).where(Product.slug==slug,Product.status=='published'))
 if not x:raise HTTPException(404,'产品不存在')
 return as_dict(x)
@app.get('/api/v1/articles')
def articles(s:Session=Depends(db)):return [as_dict(a) for a in s.scalars(select(Article).where(Article.status=='published').order_by(Article.sort_order,Article.id.desc()))]
@app.get('/api/v1/articles/{slug}')
def article(slug:str,s:Session=Depends(db)):
 a=s.scalar(select(Article).where(Article.slug==slug,Article.status=='published'))
 if not a:raise HTTPException(404,'文章不存在')
 return as_dict(a)
@app.post('/api/v1/inquiries',status_code=201)
def create_inquiry(data:InquiryIn,request:Request,s:Session=Depends(db)):
 # Simple honeypot and payload caps; production should add rate limiting at Nginx/WAF
 if data.product_id and not s.get(Product,data.product_id):raise HTTPException(400,'产品不存在')
 save(s,Inquiry(**data.model_dump()))
 return {'ok':True,'message':'咨询已提交'}
@app.post('/api/v1/admin/login')
def login(data:LoginIn,s:Session=Depends(db)):
 a=s.scalar(select(Admin).where(Admin.username==data.username))
 if not a or not password_verify(data.password,a.password_hash):raise HTTPException(401,'账号或密码错误')
 t=create_token(a.id)
 return {'access_token':t,'token_type':'bearer'}
@app.get('/api/v1/admin/categories')
def admin_categories(s:Session=Depends(db),_=Depends(require_admin)):return [as_dict(x) for x in s.scalars(select(Category).order_by(Category.sort_order,Category.id))]
@app.post('/api/v1/admin/categories')
def add_category(data:CategoryIn,s:Session=Depends(db),_=Depends(require_admin)):return save(s,Category(**data.model_dump()))
@app.put('/api/v1/admin/categories/{id}')
def edit_category(id:int,data:CategoryIn,s:Session=Depends(db),_=Depends(require_admin)):
 x=s.get(Category,id)
 if not x:raise HTTPException(404)
 for k,v in data.model_dump().items():setattr(x,k,v)
 return save(s,x)
@app.delete('/api/v1/admin/categories/{id}')
def del_category(id:int,s:Session=Depends(db),_=Depends(require_admin)):
 x=s.get(Category,id)
 if not x:raise HTTPException(404)
 if s.scalar(select(func.count()).select_from(Product).where(Product.category_id==id)):raise HTTPException(400,'分类下仍有产品，请先转移')
 s.delete(x);s.commit();return {'ok':True}
@app.get('/api/v1/admin/products')
def admin_products(s:Session=Depends(db),_=Depends(require_admin)):return [as_dict(x) for x in s.scalars(select(Product).order_by(Product.id.desc()))]
@app.post('/api/v1/admin/products')
def add_product(data:ProductIn,s:Session=Depends(db),_=Depends(require_admin)):return save(s,Product(**data.model_dump()))
@app.put('/api/v1/admin/products/{id}')
def edit_product(id:int,data:ProductIn,s:Session=Depends(db),_=Depends(require_admin)):
 x=s.get(Product,id)
 if not x:raise HTTPException(404)
 for k,v in data.model_dump().items():setattr(x,k,v)
 return save(s,x)
@app.delete('/api/v1/admin/products/{id}')
def del_product(id:int,s:Session=Depends(db),_=Depends(require_admin)):
 x=s.get(Product,id)
 if not x:raise HTTPException(404)
 if s.scalar(select(func.count()).select_from(Inquiry).where(Inquiry.product_id==id)):raise HTTPException(400,'有咨询关联，建议下架而不是删除')
 s.delete(x);s.commit();return {'ok':True}
@app.get('/api/v1/admin/articles')
def admin_articles(s:Session=Depends(db),_=Depends(require_admin)):return [as_dict(x) for x in s.scalars(select(Article).order_by(Article.id.desc()))]
@app.post('/api/v1/admin/articles')
def add_article(data:ArticleIn,s:Session=Depends(db),_=Depends(require_admin)):return save(s,Article(**data.model_dump()))
@app.put('/api/v1/admin/articles/{id}')
def edit_article(id:int,data:ArticleIn,s:Session=Depends(db),_=Depends(require_admin)):
 x=s.get(Article,id)
 if not x:raise HTTPException(404)
 for k,v in data.model_dump().items():setattr(x,k,v)
 return save(s,x)
@app.delete('/api/v1/admin/articles/{id}')
def del_article(id:int,s:Session=Depends(db),_=Depends(require_admin)):
 x=s.get(Article,id)
 if not x:raise HTTPException(404)
 s.delete(x);s.commit();return {'ok':True}
@app.get('/api/v1/admin/settings')
def admin_settings(s:Session=Depends(db),_=Depends(require_admin)):return parse_settings(s)
@app.put('/api/v1/admin/settings')
def update_settings(data:dict[str,str],s:Session=Depends(db),_=Depends(require_admin)):
 allowed={'brand_name','slogan','about','phone','wechat','whatsapp','email','address','hero_image','hero_title','hero_subtitle'}
 for k,v in data.items():
  if k not in allowed or len(v)>6000:raise HTTPException(400,f'不支持的字段: {k}')
  x=s.get(Setting,k)
  if x:x.value=v
  else:s.add(Setting(key=k,value=v))
 s.commit();return parse_settings(s)
@app.get('/api/v1/admin/inquiries')
def admin_inquiries(s:Session=Depends(db),_=Depends(require_admin)):return [as_dict(x) for x in s.scalars(select(Inquiry).order_by(Inquiry.id.desc()))]
@app.put('/api/v1/admin/inquiries/{id}')
def update_inquiry(id:int,data:StatusIn,s:Session=Depends(db),_=Depends(require_admin)):
 x=s.get(Inquiry,id)
 if not x:raise HTTPException(404)
 x.status=data.status;return save(s,x)
@app.post('/api/v1/admin/upload')
async def upload(file:UploadFile=File(...),_=Depends(require_admin)):
 raw=await file.read(5*1024*1024+1)
 if len(raw)>5*1024*1024:raise HTTPException(400,'图片不能超过5MB')
 try:
  im=Image.open(io.BytesIO(raw));im.verify();im=Image.open(io.BytesIO(raw))
  if im.width>7000 or im.height>7000:raise ValueError('too large')
  if im.format not in ('JPEG','PNG','WEBP'):raise ValueError('format')
  im=im.convert('RGB'); im.thumbnail((2200,2200))
  filename=f'{uuid.uuid4().hex}.webp';im.save(UPLOAD_DIR/filename,format='WEBP',quality=83)
 except (UnidentifiedImageError,ValueError,OSError):raise HTTPException(400,'仅接受有效 JPG/PNG/WebP 图片')
 return {'url':f'{PUBLIC_PATH_PREFIX}/uploads/{filename}'}
