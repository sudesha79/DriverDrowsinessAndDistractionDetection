from ultralytics import YOLO
model = YOLO('runs/detect/drivernew/weights/best.pt')
print(model.names)