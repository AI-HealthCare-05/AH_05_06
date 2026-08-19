from app.core import config
from app.patient.chatbot import ApprovedKnowledgeChatbot
from app.patient.contracts import InMemoryApprovedGuidanceProvider
from app.patient.messaging import InMemoryPatientMessageGateway
from app.patient.security import PatientSecretCodec
from app.patient.service import PatientFlowService
from app.patient.store import PatientFlowStore

store = PatientFlowStore()
guidance_provider = InMemoryApprovedGuidanceProvider()
message_gateway = InMemoryPatientMessageGateway()
service = PatientFlowService(
    store=store,
    guidance_provider=guidance_provider,
    message_gateway=message_gateway,
    codec=PatientSecretCodec(config.SECRET_KEY),
    public_patient_url=config.PATIENT_PUBLIC_URL,
)
chatbot = ApprovedKnowledgeChatbot()
