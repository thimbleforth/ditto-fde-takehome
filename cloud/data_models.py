# data_models.py
from sqlalchemy import Column, Integer, String, DateTime
# all the basic stuff we need for the DB
from sqlalchemy.ext.declarative import declarative_base
# declarative_base lets us define the database model

Base = declarative_base()

# create the Report class off Base
class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    report_id = Column(String(64), index=True)# logical report identifier
    title = Column(String(255))
    content = Column(String(2000))
    classification = Column(String(20)) # e.g., CUI, IL4, IL5
    updated_at = Column(DateTime(timezone=True), nullable=False)
    updated_by = Column(String(100)) # analyst ID

# nothing else happens in this .py, the function to create a new record in 'reports' happens inside the cloud_app.py file.

# the edge_app.py file will handle the local creation of the same schema and send it up to the cloud app.

