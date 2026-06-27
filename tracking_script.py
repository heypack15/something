import cv2
from ultralytics import YOLOWorld

# Инициализируем модель
model = YOLOWorld(r'C:\Users\User\Desktop\tj\yolo\best.pt')

my_classes= ["drone"]
model.set_classes(my_classes)

# Открываем видео (0 для веб-камеры или путь к файлу 'video.mp4')
cap = cv2.VideoCapture(r'C:\Users\User\Desktop\tj\yolo\2026-05-07_13-40-10.mp4')

# Координаты линии растяжки
line_start = (960, 195)
line_end = (960, 615)

# Словарь для хранения предыдущего положения объектов {object_id: side}
track_history = {}
counter = 0  # Счетчик пересечений

def get_side(A, B, P):
    """Определяет, с какой стороны от линии AB находится точка P"""
    return (B[0] - A[0]) * (P[1] - A[1]) - (B[1] - A[1]) * (P[0] - A[0])

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    # Запускаем YOLO с трекером (persist=True сохраняет ID между кадрами)
    results = model.track(frame, persist=True, verbose=False)[0]

    # Рисуем линию растяжки (синяя)
    cv2.line(frame, line_start, line_end, (255, 0, 0), 3)

    if results.boxes.id is not None:
        boxes = results.boxes.xyxy.cpu().numpy()
        track_ids = results.boxes.id.cpu().numpy().astype(int)
        clss = results.boxes.cls.cpu().numpy().astype(int)

        for box, track_id, cls in zip(boxes, track_ids, clss):
            x1, y1, x2, y2 = map(int, box)
            
            # Берем нижнюю центральную точку объекта ("ноги")
            cx = int((x1 + x2) / 2)
            cy = y2
            p_current = (cx, cy)

            # Определяем, с какой стороны линии точка сейчас
            current_side = get_side(line_start, line_end, p_current)
            
            # Нормализуем сторону: > 0 это 1, < 0 это -1
            current_side_sign = 1 if current_side > 0 else -1

            # Если мы уже видели этот объект в предыдущих кадрах
            if track_id in track_history:
                prev_side_sign = track_history[track_id]

                # Если знак изменился — линия пересечена!
                if prev_side_sign != current_side_sign:
                    counter += 1
                    print(f"🚨 Объект {track_id} ({model.names[cls]}) пересек линию! Всего: {counter}")
                    
                    # Подсвечиваем рамку красным в момент пересечения
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
                    cv2.putText(frame, "CROSSING!", (x1, y1 - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                else:
                    # Обычное движение
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            else:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Обновляем историю для этого ID
            track_history[track_id] = current_side_sign
            
            # Точка на «ногах» объекта
            cv2.circle(frame, p_current, 5, (0, 255, 255), -1)
            cv2.putText(frame, f"ID: {track_id}", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Выводим счетчик на экран
    cv2.putText(frame, f"Crossings: {counter}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 3)

    cv2.imshow("YOLOv8 Tripwire Video", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()