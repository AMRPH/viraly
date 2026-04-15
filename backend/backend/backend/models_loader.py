import torch
from faster_whisper import WhisperModel, BatchedInferencePipeline
from transformers import RobertaTokenizer, RobertaForSequenceClassification
from ultralytics import YOLO

model_whisper = None
model_interesting = None
tokenizer_interesting = None
model_tracking = None

def load_models():
    global model_whisper, model_interesting, tokenizer_interesting, model_tracking
    print("Loading models into VRAM...")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print('Device: ' + device)


    model = WhisperModel("large-v3-turbo", device=device, compute_type="float16")
    model_whisper = BatchedInferencePipeline(model=model)

    model_path = "backend/models/ruRoberta-large-v3"
    tokenizer_interesting = RobertaTokenizer.from_pretrained(model_path)
    model_interesting = RobertaForSequenceClassification.from_pretrained(model_path).to(device).eval()

    model_path = "backend/models/yolov12n-face.pt"
    model_tracking = YOLO(model_path).to(device).eval()

    print("Models loaded successfully")

