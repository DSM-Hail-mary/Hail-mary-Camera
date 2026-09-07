"""Zone polygon calibration.

Click points on a live camera frame to define a zone polygon, then save it to
a JSON file (Hail_Mary/edge/zones.py-compatible) that pipeline.py can load
via --zone-file. save_polygon()/load_polygon() are pure file I/O and tested
with real temp files; main() is the interactive click-to-define loop,
exercised manually (real camera/display), same as capture.py/preview.py.
"""

import json

WINDOW_NAME = "Hail-Mary zone calibration"


def save_polygon(path, zone_id, polygon):
    data = {"zone_id": zone_id, "polygon": [[float(x), float(y)] for x, y in polygon]}
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_polygon(path):
    with open(path) as f:
        data = json.load(f)
    return data["zone_id"], [tuple(point) for point in data["polygon"]]


def main(zone_id="hall_main", out_path="zone.json", camera_source=0):  # pragma: no cover
    import cv2

    from Hail_Mary.edge.capture import open_source, stream_frames

    points = []

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))

    cap = open_source(backend="opencv", source=camera_source)
    if not cap.isOpened():
        raise SystemExit("Failed to open camera")

    cv2.namedWindow(WINDOW_NAME)
    cv2.setMouseCallback(WINDOW_NAME, on_click)
    print("Click zone corners (left click). 's' save, 'c' clear, 'q' quit.", flush=True)

    try:
        for frame in stream_frames(cap):
            display = frame.copy()
            for i, point in enumerate(points):
                cv2.circle(display, point, 5, (0, 255, 0), -1)
                if i > 0:
                    cv2.line(display, points[i - 1], point, (0, 255, 0), 2)
            if len(points) > 2:
                cv2.line(display, points[-1], points[0], (0, 255, 0), 1)

            cv2.imshow(WINDOW_NAME, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            if key == ord("c"):
                points.clear()
            if key == ord("s"):
                if len(points) < 3:
                    print("need at least 3 points to save a polygon", flush=True)
                else:
                    save_polygon(out_path, zone_id, points)
                    print(f"saved {len(points)}-point polygon to {out_path}", flush=True)
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def _parse_args():  # pragma: no cover
    import argparse
    parser = argparse.ArgumentParser(description="Click to define a zone polygon on the live camera feed")
    parser.add_argument("--zone-id", default="hall_main")
    parser.add_argument("--out", default="zone.json")
    parser.add_argument("--source", type=int, default=0)
    return parser.parse_args()


if __name__ == "__main__":  # pragma: no cover
    _args = _parse_args()
    main(zone_id=_args.zone_id, out_path=_args.out, camera_source=_args.source)
