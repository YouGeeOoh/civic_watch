from __future__ import annotations
import os, uuid, enum, shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any

import jwt
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import (create_engine, String, Text, Boolean, DateTime, Integer, ForeignKey,
                        JSON, Enum as SAEnum, UniqueConstraint, select, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./civicwatch.db")
SECRET_KEY = os.getenv("SECRET_KEY", "local-development-secret-change-this-before-deployment")
TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads")); UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if x.strip()]
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
password_hash = PasswordHasher()
def verify_password(plain: str, hashed: str) -> bool:
    try: return password_hash.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, Exception): return False
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
optional_bearer = HTTPBearer(auto_error=False)

class Base(DeclarativeBase): pass
class Role(str, enum.Enum):
    citizen="citizen"; lga_officer="lga_officer"; agency_officer="agency_officer"; triage_officer="triage_officer"; supervisor="supervisor"; state_admin="state_admin"; auditor="auditor"; moderator="moderator"
class Status(str, enum.Enum):
    submitted="submitted"; under_review="under_review"; verified="verified"; assigned="assigned"; in_progress="in_progress"; awaiting_information="awaiting_information"; resolved="resolved"; closed="closed"; rejected="rejected"; reopened="reopened"
class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True)
    email: Mapped[str]=mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    display_name: Mapped[str]=mapped_column(String(80))
    role: Mapped[Role]=mapped_column(SAEnum(Role), default=Role.citizen, index=True)
    lga: Mapped[Optional[str]]=mapped_column(String(100), nullable=True, index=True)
    agency_id: Mapped[Optional[str]]=mapped_column(String(100), nullable=True, index=True)
    active: Mapped[bool]=mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Report(Base):
    __tablename__="reports"
    id: Mapped[int]=mapped_column(primary_key=True)
    reference: Mapped[str]=mapped_column(String(24), unique=True, index=True)
    owner_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str]=mapped_column(String(80), index=True)
    subcategory: Mapped[Optional[str]]=mapped_column(String(100), nullable=True)
    title: Mapped[str]=mapped_column(String(180))
    description: Mapped[str]=mapped_column(Text)
    lga: Mapped[str]=mapped_column(String(100), index=True)
    community: Mapped[str]=mapped_column(String(120), index=True)
    landmark: Mapped[Optional[str]]=mapped_column(String(255), nullable=True)
    latitude: Mapped[Optional[float]]=mapped_column(nullable=True)
    longitude: Mapped[Optional[float]]=mapped_column(nullable=True)
    observed_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True), nullable=True)
    severity: Mapped[str]=mapped_column(String(20), default="medium", index=True)
    details: Mapped[dict]=mapped_column(JSON, default=dict)
    image_path: Mapped[Optional[str]]=mapped_column(String(255), nullable=True)
    status: Mapped[Status]=mapped_column(SAEnum(Status), default=Status.submitted, index=True)
    verified: Mapped[bool]=mapped_column(Boolean, default=False, index=True)
    public_visible: Mapped[bool]=mapped_column(Boolean, default=True, index=True)
    assigned_agency: Mapped[Optional[str]]=mapped_column(String(120), nullable=True, index=True)
    assigned_officer_id: Mapped[Optional[int]]=mapped_column(ForeignKey("users.id"), nullable=True)
    priority_score: Mapped[int]=mapped_column(Integer, default=0)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    owner: Mapped[User]=relationship(foreign_keys=[owner_id])
    supports: Mapped[list["Support"]]=relationship(cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]]=relationship(cascade="all, delete-orphan")
class Support(Base):
    __tablename__="supports"
    __table_args__=(UniqueConstraint("report_id","user_id",name="uq_support_report_user"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("reports.id"),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class Comment(Base):
    __tablename__="comments"
    id: Mapped[int]=mapped_column(primary_key=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("reports.id"),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    body: Mapped[str]=mapped_column(String(1500))
    hidden: Mapped[bool]=mapped_column(Boolean,default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    user: Mapped[User]=relationship()
class ReportVersion(Base):
    __tablename__="report_versions"
    id: Mapped[int]=mapped_column(primary_key=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("reports.id"),index=True)
    changed_by: Mapped[int]=mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]=mapped_column(String(255),default="Citizen edit")
    snapshot: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class StatusEvent(Base):
    __tablename__="status_events"
    id: Mapped[int]=mapped_column(primary_key=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("reports.id"),index=True)
    actor_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    from_status: Mapped[Optional[str]]=mapped_column(String(40),nullable=True)
    to_status: Mapped[str]=mapped_column(String(40))
    note: Mapped[Optional[str]]=mapped_column(Text,nullable=True)
    public_note: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class AssignmentEvent(Base):
    __tablename__="assignment_events"
    id: Mapped[int]=mapped_column(primary_key=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("reports.id"),index=True)
    actor_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    from_agency: Mapped[Optional[str]]=mapped_column(String(120),nullable=True)
    to_agency: Mapped[Optional[str]]=mapped_column(String(120),nullable=True)
    note: Mapped[Optional[str]]=mapped_column(Text,nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class InternalNote(Base):
    __tablename__="internal_notes"
    id: Mapped[int]=mapped_column(primary_key=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("reports.id"),index=True)
    author_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    body: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class AuditLog(Base):
    __tablename__="audit_logs"
    id: Mapped[int]=mapped_column(primary_key=True)
    actor_id: Mapped[Optional[int]]=mapped_column(ForeignKey("users.id"),nullable=True)
    action: Mapped[str]=mapped_column(String(100),index=True)
    entity_type: Mapped[str]=mapped_column(String(80))
    entity_id: Mapped[Optional[str]]=mapped_column(String(80),nullable=True)
    metadata_json: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc),index=True)

class RegisterIn(BaseModel):
    email: EmailStr; password: str=Field(min_length=10,max_length=128); display_name: str=Field(min_length=2,max_length=80)
class LoginIn(BaseModel): email: EmailStr; password: str
class ReportIn(BaseModel):
    category: str=Field(min_length=2,max_length=80); subcategory: Optional[str]=None
    title: str=Field(min_length=5,max_length=180); description: str=Field(min_length=20,max_length=5000)
    lga: str=Field(min_length=2,max_length=100); community: str=Field(min_length=2,max_length=120)
    landmark: Optional[str]=Field(default=None,max_length=255); latitude: Optional[float]=None; longitude: Optional[float]=None
    observed_at: Optional[datetime]=None; severity: str=Field(default="medium",pattern="^(low|medium|high|critical)$")
    details: dict[str,Any]=Field(default_factory=dict)
class EditIn(BaseModel): title: str=Field(min_length=5,max_length=180); description: str=Field(min_length=20,max_length=5000); landmark: Optional[str]=None; details: dict[str,Any]=Field(default_factory=dict); reason: str=Field(default="Citizen correction",max_length=255)
class CommentIn(BaseModel): body: str=Field(min_length=1,max_length=1500)
class AssignIn(BaseModel): agency: str=Field(min_length=2,max_length=120); officer_id: Optional[int]=None; note: Optional[str]=Field(default=None,max_length=1000)
class StatusIn(BaseModel): status: Status; note: Optional[str]=Field(default=None,max_length=2000); public_note: bool=True
class InternalNoteIn(BaseModel): body: str=Field(min_length=2,max_length=5000)
class GovernmentUserIn(BaseModel): email: EmailStr; password: str=Field(min_length=14,max_length=128); display_name: str=Field(min_length=2,max_length=80); role: Role; lga: Optional[str]=None; agency_id: Optional[str]=None
class ModerationIn(BaseModel): hidden: bool; reason: str=Field(min_length=3,max_length=500)
class UserOut(BaseModel): model_config=ConfigDict(from_attributes=True); id:int; email:str; display_name:str; role:Role; lga:Optional[str]; agency_id:Optional[str]

app=FastAPI(title="CivicWatch API",version="1.0.0",description="Civic reporting and government case-management API")
app.add_middleware(CORSMiddleware,allow_origins=ALLOWED_ORIGINS,allow_credentials=True,allow_methods=["GET","POST","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type"])
def db_session():
    db=SessionLocal()
    try: yield db
    finally: db.close()
def audit(db:Session, actor:Optional[int], action:str, entity:str, entity_id:Any=None, metadata:dict|None=None):
    db.add(AuditLog(actor_id=actor,action=action,entity_type=entity,entity_id=str(entity_id) if entity_id is not None else None,metadata_json=metadata or {}))
def token_for(user:User):
    now=datetime.now(timezone.utc)
    return jwt.encode({"sub":str(user.id),"role":user.role.value,"iat":now,"exp":now+timedelta(minutes=TOKEN_MINUTES)},SECRET_KEY,algorithm="HS256")
def current_user(token:str=Depends(oauth2),db:Session=Depends(db_session))->User:
    try: payload=jwt.decode(token,SECRET_KEY,algorithms=["HS256"]); uid=int(payload["sub"])
    except Exception: raise HTTPException(401,"Invalid or expired access token",headers={"WWW-Authenticate":"Bearer"})
    user=db.get(User,uid)
    if not user or not user.active: raise HTTPException(401,"Account unavailable")
    return user
def optional_user(credentials: Optional[HTTPAuthorizationCredentials]=Depends(optional_bearer),db:Session=Depends(db_session))->Optional[User]:
    if not credentials: return None
    try:
        payload=jwt.decode(credentials.credentials,SECRET_KEY,algorithms=["HS256"]); uid=int(payload["sub"])
        user=db.get(User,uid)
        return user if user and user.active else None
    except Exception: return None
def require_roles(*roles:Role):
    def dep(user:User=Depends(current_user)):
        if user.role not in roles: raise HTTPException(403,"You do not have permission to perform this action")
        return user
    return dep
GOV_ROLES=(Role.lga_officer,Role.agency_officer,Role.triage_officer,Role.supervisor,Role.state_admin,Role.auditor)
ASSIGN_ROLES=(Role.triage_officer,Role.supervisor,Role.state_admin,Role.lga_officer)
WRITE_STATUS_ROLES=(Role.lga_officer,Role.agency_officer,Role.triage_officer,Role.supervisor,Role.state_admin)
def can_view_report(user:User,r:Report)->bool:
    if user.role==Role.state_admin or user.role in (Role.triage_officer,Role.supervisor,Role.auditor): return True
    if user.role==Role.lga_officer: return user.lga==r.lga
    if user.role==Role.agency_officer: return user.agency_id is not None and user.agency_id==r.assigned_agency
    return user.id==r.owner_id or r.public_visible

def report_dict(db:Session,r:Report,user:Optional[User]=None,public:bool=True):
    supports=db.scalar(select(func.count(Support.id)).where(Support.report_id==r.id)) or 0
    my_support=bool(user and db.scalar(select(Support.id).where(Support.report_id==r.id,Support.user_id==user.id)))
    comments=db.scalars(select(Comment).where(Comment.report_id==r.id,Comment.hidden==False).order_by(Comment.created_at.asc())).all()
    events=db.scalars(select(StatusEvent).where(StatusEvent.report_id==r.id,StatusEvent.public_note==True).order_by(StatusEvent.created_at.asc())).all()
    out={"id":r.id,"reference":r.reference,"category":r.category,"subcategory":r.subcategory,"title":r.title,"description":r.description,"lga":r.lga,"community":r.community,"landmark":r.landmark,"latitude":r.latitude,"longitude":r.longitude,"observed_at":r.observed_at.isoformat() if r.observed_at else None,"severity":r.severity,"details":r.details,"image_url":f"/uploads/{r.image_path}" if r.image_path else None,"status":r.status.value,"verified":r.verified,"assigned_agency":r.assigned_agency if (not public or (user and user.role in GOV_ROLES)) else None,"support_count":supports,"supported_by_me":my_support,"owner_id":r.owner_id,"owner_name":r.owner.display_name if r.owner else "Citizen","created_at":r.created_at.isoformat(),"updated_at":r.updated_at.isoformat(),"comments":[{"id":c.id,"body":c.body,"author":c.user.display_name if c.user else "Citizen","created_at":c.created_at.isoformat()} for c in comments],"status_history":[{"from_status":e.from_status,"to_status":e.to_status,"note":e.note,"created_at":e.created_at.isoformat()} for e in events]}
    if user and user.id==r.owner_id: out["can_edit"]=r.status in (Status.submitted,Status.under_review,Status.reopened)
    return out

def create_status_event(db,report,actor,to_status,note=None,public_note=True):
    old=report.status.value if report.status else None
    report.status=to_status
    db.add(StatusEvent(report_id=report.id,actor_id=actor.id,from_status=old,to_status=to_status.value,note=note,public_note=public_note))

def seed():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        email=os.getenv("ADMIN_EMAIL","admin@civicwatch.ng").lower()
        if not db.scalar(select(User.id).where(User.email==email)):
            pw=os.getenv("ADMIN_PASSWORD","ChangeThisDemoPassword123!")
            db.add(User(email=email,password_hash=password_hash.hash(pw),display_name="CivicWatch State Admin",role=Role.state_admin))
        db.commit()
        # Categories are exposed as a stable list in /categories; routing must be configured with government.

@app.on_event("startup")
def startup(): seed()
@app.get("/health")
def health(): return {"status":"ok","service":"civicwatch-api"}
@app.get("/categories")
def categories():
    return [{"name":"Waste & Sanitation","fields":["waste_type","duration","drainage_blocked"]},{"name":"Roads & Potholes","fields":["road_condition","passable","hazard_type"]},{"name":"Drainage & Flooding","fields":["drainage_type","water_level","duration"]},{"name":"Public Infrastructure","fields":["asset_type","asset_condition"]},{"name":"Water & Public Utilities","fields":["utility_type","service_affected","duration"]},{"name":"Public Lighting","fields":["light_type","number_affected"]},{"name":"Road Accessibility & Safety","fields":["hazard_type","passable","traffic_impact"]},{"name":"Other Civic Issue","fields":["issue_type"]}]
@app.post("/auth/register")
def register(data:RegisterIn,db:Session=Depends(db_session)):
    email=data.email.lower().strip()
    if db.scalar(select(User.id).where(User.email==email)): raise HTTPException(409,"An account with this email already exists")
    u=User(email=email,password_hash=password_hash.hash(data.password),display_name=data.display_name.strip(),role=Role.citizen)
    db.add(u); db.flush(); audit(db,u.id,"user.register","user",u.id); db.commit()
    return {"access_token":token_for(u),"token_type":"bearer","user":UserOut.model_validate(u).model_dump(mode="json")}
@app.post("/auth/login")
def login(data:LoginIn,db:Session=Depends(db_session)):
    u=db.scalar(select(User).where(User.email==data.email.lower().strip()))
    if not u or not verify_password(data.password,u.password_hash) or not u.active: raise HTTPException(401,"Incorrect email or password")
    audit(db,u.id,"auth.login","user",u.id); db.commit()
    return {"access_token":token_for(u),"token_type":"bearer","user":UserOut.model_validate(u).model_dump(mode="json")}
@app.get("/auth/me",response_model=UserOut)
def me(user:User=Depends(current_user)): return user
@app.get("/feed")
def feed(category:Optional[str]=None,lga:Optional[str]=None,status:Optional[Status]=None,q:Optional[str]=None,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),user:Optional[User]=Depends(optional_user),db:Session=Depends(db_session)):
    # Public feed does not require authentication; optional token support is handled by /feed/me-aware clients.
    stmt=select(Report).where(Report.public_visible==True)
    if category: stmt=stmt.where(Report.category==category)
    if lga: stmt=stmt.where(Report.lga.ilike(f"%{lga}%"))
    if status: stmt=stmt.where(Report.status==status)
    if q: stmt=stmt.where((Report.title.ilike(f"%{q}%"))|(Report.description.ilike(f"%{q}%"))|(Report.community.ilike(f"%{q}%")))
    rows=db.scalars(stmt.order_by(Report.created_at.desc()).offset(offset).limit(limit)).all()
    return [report_dict(db,r,None,True) for r in rows]
@app.get("/reports/mine")
def my_reports(user:User=Depends(current_user),db:Session=Depends(db_session)):
    rows=db.scalars(select(Report).where(Report.owner_id==user.id).order_by(Report.created_at.desc())).all()
    return [report_dict(db,r,user,False) for r in rows]
@app.post("/reports")
def create_report(data:ReportIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    allowed_categories={"Waste & Sanitation","Roads & Potholes","Drainage & Flooding","Public Infrastructure","Water & Public Utilities","Public Lighting","Road Accessibility & Safety","Other Civic Issue"}
    if data.category not in allowed_categories: raise HTTPException(422,"Select a supported civic issue category")
    if user.role!=Role.citizen: raise HTTPException(403,"Government accounts cannot submit citizen reports")
    if (data.latitude is None) != (data.longitude is None): raise HTTPException(422,"Provide both latitude and longitude, or neither")
    if data.latitude is not None and not (-90<=data.latitude<=90 and -180<=data.longitude<=180): raise HTTPException(422,"Invalid coordinates")
    ref="CW-AN-"+uuid.uuid4().hex[:8].upper()
    r=Report(reference=ref,owner_id=user.id,category=data.category,subcategory=data.subcategory,title=data.title.strip(),description=data.description.strip(),lga=data.lga.strip(),community=data.community.strip(),landmark=data.landmark,latitude=data.latitude,longitude=data.longitude,observed_at=data.observed_at,severity=data.severity,details=data.details,status=Status.submitted)
    db.add(r); db.flush(); db.add(StatusEvent(report_id=r.id,actor_id=user.id,from_status=None,to_status=Status.submitted.value,note="Report received",public_note=True)); audit(db,user.id,"report.create","report",r.id,{"reference":ref}); db.commit(); db.refresh(r)
    return report_dict(db,r,user,False)
@app.post("/reports/{report_id}/upload")
def upload_image(report_id:int,file:UploadFile=File(...),user:User=Depends(current_user),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r: raise HTTPException(404,"Report not found")
    if r.owner_id!=user.id and user.role not in (Role.state_admin,Role.moderator): raise HTTPException(403,"Not allowed")
    if r.status not in (Status.submitted,Status.under_review,Status.reopened): raise HTTPException(409,"Evidence cannot be changed at this stage; submit a follow-up instead")
    allowed={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}
    if file.content_type not in allowed: raise HTTPException(415,"Only JPG, PNG, and WEBP images are accepted")
    data=file.file.read(5*1024*1024+1)
    if not data or len(data)>5*1024*1024: raise HTTPException(413,"Image must be smaller than 5 MB")
    # Production must add content sniffing, malware scanning, EXIF stripping, and private object storage.
    name=f"{uuid.uuid4().hex}{allowed[file.content_type]}"; (UPLOAD_DIR/name).write_bytes(data)
    r.image_path=name; audit(db,user.id,"report.upload","report",r.id,{"file":name}); db.commit()
    return {"image_url":f"/uploads/{name}"}
@app.get("/reports/{report_id}")
def get_report(report_id:int,user:Optional[User]=Depends(optional_user),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r or (not r.public_visible and (not user or (user.id!=r.owner_id and user.role not in (*GOV_ROLES, Role.moderator)))): raise HTTPException(404,"Report not found")
    return report_dict(db,r,user,not bool(user and user.id==r.owner_id))
@app.patch("/reports/{report_id}")
def edit_report(report_id:int,data:EditIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r: raise HTTPException(404,"Report not found")
    if r.owner_id!=user.id: raise HTTPException(403,"Only the report owner can edit this report")
    if r.status not in (Status.submitted,Status.under_review,Status.reopened): raise HTTPException(409,"This report is already assigned or further along. Submit a correction request through the case page.")
    snapshot={"title":r.title,"description":r.description,"landmark":r.landmark,"details":r.details,"changed_at":datetime.now(timezone.utc).isoformat()}
    db.add(ReportVersion(report_id=r.id,changed_by=user.id,reason=data.reason,snapshot=snapshot))
    r.title=data.title.strip(); r.description=data.description.strip(); r.landmark=data.landmark; r.details=data.details
    audit(db,user.id,"report.edit","report",r.id,{"reason":data.reason}); db.commit(); db.refresh(r)
    return report_dict(db,r,user,False)
@app.post("/reports/{report_id}/support")
def toggle_support(report_id:int,user:User=Depends(current_user),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r or not r.public_visible: raise HTTPException(404,"Report not found")
    if r.owner_id==user.id: raise HTTPException(400,"You cannot support your own report")
    existing=db.scalar(select(Support).where(Support.report_id==r.id,Support.user_id==user.id))
    if existing: db.delete(existing); supported=False
    else: db.add(Support(report_id=r.id,user_id=user.id)); supported=True
    audit(db,user.id,"report.support" if supported else "report.unsupport","report",r.id); db.commit()
    count=db.scalar(select(func.count(Support.id)).where(Support.report_id==r.id)) or 0
    return {"supported":supported,"support_count":count,"meaning":"Public support indicates concern, not verification."}
@app.post("/reports/{report_id}/comments")
def add_comment(report_id:int,data:CommentIn,user:User=Depends(current_user),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r or not r.public_visible: raise HTTPException(404,"Report not found")
    body=data.body.strip()
    if len(body)<1: raise HTTPException(422,"Comment cannot be empty")
    # Human moderation and stronger abuse prevention are required before production.
    c=Comment(report_id=r.id,user_id=user.id,body=body); db.add(c); audit(db,user.id,"comment.create","comment",None,{"report_id":r.id}); db.commit(); db.refresh(c)
    return {"id":c.id,"body":c.body,"author":user.display_name,"created_at":c.created_at.isoformat()}
@app.get("/government/queue")
def government_queue(status:Optional[Status]=None,lga:Optional[str]=None,category:Optional[str]=None,db:Session=Depends(db_session),user:User=Depends(require_roles(*GOV_ROLES))):
    stmt=select(Report)
    if user.role==Role.lga_officer: stmt=stmt.where(Report.lga==user.lga)
    elif user.role==Role.agency_officer: stmt=stmt.where(Report.assigned_agency==user.agency_id)
    if status: stmt=stmt.where(Report.status==status)
    if lga and user.role!=Role.lga_officer: stmt=stmt.where(Report.lga==lga)
    if category: stmt=stmt.where(Report.category==category)
    rows=db.scalars(stmt.order_by(Report.created_at.desc()).limit(300)).all()
    return [report_dict(db,r,user,False) for r in rows if can_view_report(user,r)]
@app.post("/government/reports/{report_id}/assign")
def assign_report(report_id:int,data:AssignIn,user:User=Depends(require_roles(*ASSIGN_ROLES)),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r: raise HTTPException(404,"Report not found")
    if user.role==Role.lga_officer and r.lga!=user.lga: raise HTTPException(403,"You can only route reports in your assigned LGA")
    old=r.assigned_agency; r.assigned_agency=data.agency.strip(); r.assigned_officer_id=data.officer_id
    db.add(AssignmentEvent(report_id=r.id,actor_id=user.id,from_agency=old,to_agency=r.assigned_agency,note=data.note))
    if r.status in (Status.submitted,Status.under_review,Status.verified,Status.reopened): create_status_event(db,r,user,Status.assigned,data.note,True)
    audit(db,user.id,"report.assign","report",r.id,{"from":old,"to":r.assigned_agency}); db.commit(); return {"ok":True,"reference":r.reference,"assigned_agency":r.assigned_agency,"status":r.status.value}
@app.patch("/government/reports/{report_id}/status")
def update_status(report_id:int,data:StatusIn,user:User=Depends(require_roles(*WRITE_STATUS_ROLES)),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r: raise HTTPException(404,"Report not found")
    if user.role==Role.lga_officer and r.lga!=user.lga: raise HTTPException(403,"Outside your LGA scope")
    if user.role==Role.agency_officer and r.assigned_agency!=user.agency_id: raise HTTPException(403,"This report is not assigned to your agency")
    if data.status in (Status.assigned,Status.in_progress,Status.resolved,Status.closed) and not r.assigned_agency and data.status!=Status.assigned: raise HTTPException(409,"Assign the report to an authority before this status")
    if data.status==Status.verified: r.verified=True
    if data.status==Status.reopened: r.verified=False
    create_status_event(db,r,user,data.status,data.note,data.public_note)
    audit(db,user.id,"report.status_change","report",r.id,{"status":data.status.value,"public_note":data.public_note}); db.commit()
    return {"ok":True,"reference":r.reference,"status":r.status.value,"verified":r.verified}
@app.post("/government/reports/{report_id}/internal-notes")
def add_internal_note(report_id:int,data:InternalNoteIn,user:User=Depends(require_roles(*WRITE_STATUS_ROLES)),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r or not can_view_report(user,r): raise HTTPException(404,"Report not found")
    db.add(InternalNote(report_id=r.id,author_id=user.id,body=data.body.strip())); audit(db,user.id,"report.internal_note","report",r.id); db.commit(); return {"ok":True}
@app.get("/government/reports/{report_id}/history")
def case_history(report_id:int,user:User=Depends(require_roles(*GOV_ROLES)),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r or not can_view_report(user,r): raise HTTPException(404,"Report not found")
    statuses=db.scalars(select(StatusEvent).where(StatusEvent.report_id==r.id).order_by(StatusEvent.created_at.asc())).all()
    assignments=db.scalars(select(AssignmentEvent).where(AssignmentEvent.report_id==r.id).order_by(AssignmentEvent.created_at.asc())).all()
    versions=db.scalars(select(ReportVersion).where(ReportVersion.report_id==r.id).order_by(ReportVersion.created_at.asc())).all()
    notes=[]
    if user.role!=Role.auditor:
        ns=db.scalars(select(InternalNote).where(InternalNote.report_id==r.id).order_by(InternalNote.created_at.asc())).all()
        notes=[{"id":n.id,"body":n.body,"author_id":n.author_id,"created_at":n.created_at.isoformat()} for n in ns]
    return {"status_history":[{"from_status":e.from_status,"to_status":e.to_status,"note":e.note if e.public_note or user.role!=Role.citizen else None,"public":e.public_note,"actor_id":e.actor_id,"created_at":e.created_at.isoformat()} for e in statuses],"assignment_history":[{"from_agency":e.from_agency,"to_agency":e.to_agency,"note":e.note,"actor_id":e.actor_id,"created_at":e.created_at.isoformat()} for e in assignments],"versions":[{"id":v.id,"reason":v.reason,"snapshot":v.snapshot,"changed_by":v.changed_by,"created_at":v.created_at.isoformat()} for v in versions],"internal_notes":notes}
@app.get("/government/analytics")
def analytics(user:User=Depends(require_roles(*GOV_ROLES)),db:Session=Depends(db_session)):
    stmt=select(Report)
    if user.role==Role.lga_officer: stmt=stmt.where(Report.lga==user.lga)
    elif user.role==Role.agency_officer: stmt=stmt.where(Report.assigned_agency==user.agency_id)
    reports=db.scalars(stmt).all()
    by_category={}; by_lga={}; by_status={}; by_severity={}
    for r in reports:
        by_category[r.category]=by_category.get(r.category,0)+1; by_lga[r.lga]=by_lga.get(r.lga,0)+1; by_status[r.status.value]=by_status.get(r.status.value,0)+1; by_severity[r.severity]=by_severity.get(r.severity,0)+1
    open_count=sum(1 for r in reports if r.status not in (Status.resolved,Status.closed,Status.rejected))
    verified=sum(1 for r in reports if r.verified)
    return {"total_reports":len(reports),"open_reports":open_count,"resolved_reports":sum(1 for r in reports if r.status in (Status.resolved,Status.closed)),"verified_reports":verified,"verification_rate":round(verified/len(reports)*100,1) if reports else 0,"by_category":by_category,"by_lga":by_lga,"by_status":by_status,"by_severity":by_severity,"note":"Submission counts are not confirmed incident counts. Interpret trends alongside verification, duplicate handling, and adoption."}
@app.get("/government/audit-logs")
def audit_logs(limit:int=Query(100,ge=1,le=500),user:User=Depends(require_roles(Role.state_admin,Role.auditor)),db:Session=Depends(db_session)):
    rows=db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [{"id":x.id,"actor_id":x.actor_id,"action":x.action,"entity_type":x.entity_type,"entity_id":x.entity_id,"metadata":x.metadata_json,"created_at":x.created_at.isoformat()} for x in rows]
@app.get("/uploads/{filename}")
def uploaded_file(filename:str):
    # Development only. Production must use private storage + authorization-aware signed URLs.
    from fastapi.responses import FileResponse
    if "/" in filename or "\\" in filename or filename.startswith("."): raise HTTPException(404,"Not found")
    p=UPLOAD_DIR/filename
    if not p.exists(): raise HTTPException(404,"Not found")
    return FileResponse(p)

@app.post("/government/users",response_model=UserOut)
def create_government_user(data:GovernmentUserIn,user:User=Depends(require_roles(Role.state_admin)),db:Session=Depends(db_session)):
    email=data.email.lower().strip()
    if data.role==Role.citizen: raise HTTPException(422,"Use public registration for citizen accounts")
    if data.role==Role.lga_officer and not data.lga: raise HTTPException(422,"An LGA officer must be assigned an LGA")
    if data.role==Role.agency_officer and not data.agency_id: raise HTTPException(422,"An agency officer must be assigned an agency")
    if db.scalar(select(User.id).where(User.email==email)): raise HTTPException(409,"An account with this email already exists")
    target=User(email=email,password_hash=password_hash.hash(data.password),display_name=data.display_name.strip(),role=data.role,lga=data.lga,agency_id=data.agency_id)
    db.add(target); db.flush(); audit(db,user.id,"government.user_create","user",target.id,{"role":data.role.value,"lga":data.lga,"agency_id":data.agency_id}); db.commit(); db.refresh(target)
    return target
@app.patch("/government/reports/{report_id}/visibility")
def moderate_report(report_id:int,data:ModerationIn,user:User=Depends(require_roles(Role.moderator,Role.state_admin)),db:Session=Depends(db_session)):
    r=db.get(Report,report_id)
    if not r: raise HTTPException(404,"Report not found")
    r.public_visible=not data.hidden
    audit(db,user.id,"report.hide" if data.hidden else "report.restore","report",r.id,{"reason":data.reason})
    db.commit(); return {"ok":True,"public_visible":r.public_visible,"reference":r.reference}
@app.patch("/government/comments/{comment_id}/visibility")
def moderate_comment(comment_id:int,data:ModerationIn,user:User=Depends(require_roles(Role.moderator,Role.state_admin)),db:Session=Depends(db_session)):
    c=db.get(Comment,comment_id)
    if not c: raise HTTPException(404,"Comment not found")
    c.hidden=data.hidden
    audit(db,user.id,"comment.hide" if data.hidden else "comment.restore","comment",c.id,{"reason":data.reason})
    db.commit(); return {"ok":True,"hidden":c.hidden}
