"""Live YOLOv8n + ByteTrack preview against the laptop webcam.

Run (as a module, so the Hail_Mary package resolves): python -m Hail_Mary.vision.preview
Draws a box + track_id per detected person and prints the per-frame person
count. Uses capture.py's stream_frames() -- the same M1 capture interface
M2 (aggregator.py) will eventually consume.
"""

import time

import cv2

from Hail_Mary.edge.capture import open_source, stream_frames
from Hail_Mary.vision.detect import DEFAULT_MIN_CONF, boxes_from_result, extract_person_detections, load_model

WINDOW_NAME = "Hail-Mary YOLOv8n preview"


def main():  # pragma: no cover -- interactive CLI loop, needs real camera/display/model
    print("loading YOLOv8n...", flush=True)
    model = load_model("yolov8n.pt")
    print("model loaded, opening camera...", flush=True)
    cap = open_source(backend="opencv", source=0, width=1280, height=720)
    if not cap.isOpened():
        raise SystemExit("Failed to open camera")
    print("camera opened, starting loop", flush=True)

    frame_i = 0
    try:
        for frame in stream_frames(cap):
            frame_i += 1
            result = model.track(frame, persist=True, verbose=False, classes=[0])[0]
            boxes = boxes_from_result(result)
            detections = extract_person_detections(time.time(), boxes, min_conf=DEFAULT_MIN_CONF)["detections"]

            for det in detections:
                x1, y1, x2, y2 = (int(v) for v in det["bbox"])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"id {det['track_id']} {det['conf']:.2f}", (x1, max(y1 - 8, 0)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            cv2.putText(frame, f"people: {len(detections)}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 140, 255), 2)
            if frame_i % 15 == 0:
                print(f"frame {frame_i}: people={len(detections)}", flush=True)
            cv2.imshow(WINDOW_NAME, frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":  # pragma: no cover
    main()
