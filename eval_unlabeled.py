"""
eval_unlabeled.py — 라벨 없는 "운용점 탐색" 도구 (⚠ 정확도 평가 아님)

GT(정답 라벨)가 없을 때, 모델을 이미지/영상/카메라에 돌려
  - confidence 점수 분포(히스토그램)
  - threshold별 검출 수 / 이미지당 검출 수 / 커버리지(검출≥1 이미지 비율)
만 집계한다.

⚠ 중요: GT가 없으므로 **Precision/Recall/F1/TP/FP/FN은 계산 불가**.
  어떤 검출이 '맞는지'를 알 수 없어, 여기 수치는 '검출이 얼마나 나오는가(양/분포)'일 뿐
  '얼마나 정확한가'가 아니다. 운용점은 이 거동 + 실제 눈 확인으로 '감'만 잡는 용도.
  제대로 된 운용점은 라벨된 val셋으로 eval_model.py를 돌려야 함.

입력(택1):  --images <dir> | --video <file> | --camera <N프레임>
실행 예:
  python eval_unlabeled.py --images some_imgs/ --out dist.csv --plot dist.png
  python eval_unlabeled.py --camera 300           # 카메라 300프레임(실주행 영상 권장)
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np

import model_config

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


def iter_images(images_dir):
    files = []
    for e in IMG_EXTS:
        files += glob.glob(os.path.join(images_dir, "**", "*" + e), recursive=True)
    for p in sorted(files):
        import cv2
        im = cv2.imread(p)
        if im is not None:
            yield im


def iter_video(path, stride):
    import cv2
    cap = cv2.VideoCapture(path)
    i = 0
    while True:
        ok, im = cap.read()
        if not ok:
            break
        if i % stride == 0:
            yield im
        i += 1
    cap.release()


def iter_camera(n):
    from camera import Camera, CameraConfig
    cam = Camera(CameraConfig()).start()
    try:
        got = 0
        while got < n:
            f = cam.read(timeout=2.0)
            if f is None:
                continue
            got += 1
            yield f.image
    finally:
        cam.stop()


def main():
    ap = argparse.ArgumentParser(description="라벨 없는 운용점 탐색(정확도 아님)")
    ap.add_argument("--engine", default=model_config.ENGINE)
    ap.add_argument("--images", default=None)
    ap.add_argument("--video", default=None)
    ap.add_argument("--camera", type=int, default=0, help="카메라 N프레임 캡처")
    ap.add_argument("--video-stride", type=int, default=5)
    ap.add_argument("--conf-min", type=float, default=0.001)
    ap.add_argument("--nms-iou", type=float, default=0.7)
    ap.add_argument("--imgsz", type=int, default=model_config.IMGSZ)
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--out", default="unlabeled_dist.csv")
    ap.add_argument("--plot", default="unlabeled_dist.png")
    a = ap.parse_args()

    if not (a.images or a.video or a.camera):
        raise SystemExit("--images / --video / --camera 중 하나를 지정하세요")

    from ultralytics import YOLO
    model = YOLO(a.engine, task="detect")
    names = model.names
    classes = sorted(names.keys())

    if a.images:
        src = iter_images(a.images)
    elif a.video:
        src = iter_video(a.video, a.video_stride)
    else:
        src = iter_camera(a.camera)

    # 집계: 클래스별 (score 리스트), 이미지별 클래스별 최고 score(커버리지용)
    scores = {c: [] for c in classes}
    per_img_max = {c: [] for c in classes}
    n_img = 0
    for im in src:
        r = model.predict(im, conf=a.conf_min, iou=a.nms_iou, imgsz=a.imgsz, verbose=False)[0]
        n_img += 1
        best = {c: 0.0 for c in classes}
        for b in r.boxes:
            c = int(b.cls); s = float(b.conf)
            scores[c].append(s)
            best[c] = max(best[c], s)
        for c in classes:
            per_img_max[c].append(best[c])
        if n_img % 50 == 0:
            print(f"[dist] {n_img} 프레임 처리")

    if n_img == 0:
        raise SystemExit("처리된 이미지가 없습니다")

    print(f"\n처리 이미지: {n_img}장  (⚠ GT 없음 → 정밀도/재현율 아님, 검출 '양/분포'만)")
    thresholds = [round(x, 4) for x in np.arange(a.step, 1.0, a.step)]
    rows = []
    for c in classes:
        sc = np.array(scores[c]); pim = np.array(per_img_max[c])
        print(f"\n===== class={names[c]} (총 검출 {len(sc)}개, conf≥0.001 기준) =====")
        print(f"{'conf':>6} {'검출수':>7} {'img당':>7} {'커버리지':>8}")
        for t in thresholds:
            cnt = int((sc >= t).sum())
            cov = float((pim >= t).mean())        # 검출≥1 이미지 비율
            print(f"{t:6.2f} {cnt:7d} {cnt/n_img:7.2f} {cov*100:7.1f}%")
            rows.append([names[c], t, cnt, round(cnt / n_img, 3), round(cov, 4)])

    with open(a.out, "w") as f:
        f.write("class,conf,detections,per_image,coverage\n")
        for row in rows:
            f.write(",".join(str(x) for x in row) + "\n")
    print(f"\n[dist] CSV 저장: {a.out}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
        for c in classes:
            if scores[c]:
                ax1.hist(scores[c], bins=np.arange(0, 1.01, 0.05), alpha=0.5, label=names[c])
        ax1.set_title("confidence distribution (NOT accuracy)"); ax1.set_xlabel("confidence"); ax1.set_ylabel("detections"); ax1.legend()
        for c in classes:
            sc = np.array(scores[c])
            ax2.plot(thresholds, [int((sc >= t).sum()) / n_img for t in thresholds], marker="o", ms=3, label=names[c])
        ax2.set_title("detections per image vs threshold"); ax2.set_xlabel("conf threshold"); ax2.set_ylabel("detections / image"); ax2.legend(); ax2.grid(alpha=0.3)
        plt.savefig(a.plot, dpi=120, bbox_inches="tight")
        print(f"[dist] 그래프 저장: {a.plot}")
    except Exception as e:
        print(f"[dist] PNG 생략({e})")

    print("\n⚠ 이 수치는 '검출이 얼마나 나오는가'일 뿐 '정확한가'가 아님. "
          "운용점 확정은 라벨된 val셋 + eval_model.py 필요.")


if __name__ == "__main__":
    main()
