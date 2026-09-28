from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey, inspect, text
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import bcrypt  # Changed from passlib
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vapi_calls.db")

# Create engine
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Create session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"  # FIXED: Changed from _tablename_ to __tablename__
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relationships
    calls = relationship("Call", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    
    def verify_password(self, password: str) -> bool:
        """Verify a plain password against the stored hash."""
        try:
            password_bytes = password.encode('utf-8')
            if len(password_bytes) > 72:
                return False
            return bcrypt.checkpw(password_bytes, self.hashed_password.encode('utf-8'))
        except Exception as e:
            print(f"Password verification error: {e}")
            return False
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storing; reject values beyond bcrypt's 72-byte limit."""
        try:
            password_bytes = password.encode('utf-8')
            if len(password_bytes) > 72:
                raise ValueError('Password must be no more than 72 UTF-8 bytes')
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password_bytes, salt)
            return hashed.decode('utf-8')
        except Exception as e:
            print(f"Password hashing error: {e}")
            raise ValueError(f"Password could not be hashed: {str(e)}")


class Call(Base):
    __tablename__ = "calls"  # FIXED: Changed from _tablename_ to __tablename__
    
    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    phone_number = Column(String(20), nullable=False)
    prompt = Column(Text)
    status = Column(String(50), default="initiated")
    ended_reason = Column(String(255))
    duration = Column(Integer)
    recording_url = Column(Text)
    transcript = Column(Text)
    cost = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    
    # Relationship with user
    user = relationship("User", back_populates="calls")


class Session(Base):
    __tablename__ = "sessions"  # FIXED: Changed from _tablename_ to __tablename__
    
    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(String(50))
    user_agent = Column(Text)
    
    # Relationship with user
    user = relationship("User", back_populates="sessions")


# Database helper functions
def get_db():
    """Dependency to get a new database session for each request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create missing tables and provision an admin only from explicit environment settings."""
    print("Initializing database...")
    Base.metadata.create_all(bind=engine)
    # Additive migration for existing SQLite databases; preserves existing call data.
    if "calls" in inspect(engine).get_table_names():
        call_columns = {column["name"] for column in inspect(engine).get_columns("calls")}
        if "ended_reason" not in call_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE calls ADD COLUMN ended_reason VARCHAR(255)"))
    print("Database tables checked/created successfully!")

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == admin_username).first()
        if admin_password:
            if admin_password == "admin123":
                raise ValueError("ADMIN_PASSWORD must not use the old default password")
            if admin and not admin_email:
                admin_email = admin.email
            if admin_email:
                if admin:
                    admin.email = admin_email
                    admin.hashed_password = User.hash_password(admin_password)
                    admin.is_active = True
                    admin.is_admin = True
                    admin.full_name = admin.full_name or "System Administrator"
                    print("Configured administrator credentials from environment.")
                else:
                    admin = User(
                        username=admin_username,
                        email=admin_email,
                        hashed_password=User.hash_password(admin_password),
                        full_name="System Administrator",
                        is_admin=True,
                    )
                    db.add(admin)
                    print("Created administrator from environment configuration.")
                db.commit()
            else:
                print("ADMIN_EMAIL is required with ADMIN_PASSWORD; admin provisioning skipped.")
        elif admin and admin.verify_password("admin123"):
            admin.is_active = False
            db.commit()
            print("Disabled the insecure default admin account. Set ADMIN_PASSWORD to provision it again.")
        else:
            print("No default admin account created. Set ADMIN_USERNAME, ADMIN_EMAIL, and ADMIN_PASSWORD to provision one.")
    except Exception as e:
        print(f"Error configuring admin account: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    # Running this module initializes missing tables; it never drops user data.
    init_db()
