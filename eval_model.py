"""
eval_model.py — best.engine 검출 성능 평가 (confidence threshold 스윕)

validation 데이터셋(YOLO 포맷)에 대해 conf threshold별
  Precision / Recall / F1 / TP / FP / FN
을 계산하고 전체 표 + PR curve를 출력한다.

**운용점(threshold)은 이 스크립트가 고르지 않는다.** 전체 스윕 결과와 PR curve(+CSV, PNG)만
내보내므로, 사용자가 표를 보고 직접 운용 conf를 결정한다.

데이터셋 지정 (둘 중 하나):
  --data data.yaml                 # ultralytics data.yaml의 val: 경로 사용
  --images <dir> --labels <dir>    # YOLO 포맷(images/*.jpg + labels/*.txt)

평가 방식: 표준 객체검출 매칭.
  - 추론을 아주 낮은 conf(--conf-min)로 한 번 돌려 모든 후보 박스를 얻는다.
  - 이미지/클래스별로 score 내림차순 greedy 매칭(IoU≥--iou)으로 각 예측을 TP/FP로 태깅,
    GT 수를 센다.
  - threshold t에서  TP(t)=score≥t인 TP 수,  FP(t)=score≥t인 FP 수,  FN(t)=GT−TP(t).
    → P=TP/(TP+FP), R=TP/GT, F1=2PR/(P+R).
  (AP는 참고용으로만 계산 — 운용점 선택엔 쓰지 않음)

실행(Jetson):
  python eval_model.py --engine ~/polewatch/models/best.engine --data data.yaml \
         --iou 0.5 --out eval.csv --plot pr_curve.png
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


def labels_path_for(img_path: str) -> str:
    """YOLO 관례: .../images/x.jpg → .../labels/x.txt"""
    root, _ = os.path.splitext(img_path)
    if os.sep + "images" + os.sep in img_path:
        root = root.replace(os.sep + "images" + os.sep, os.sep + "labels" + os.sep)
    return root + ".txt"


def list_val_images(data_yaml, images_dir):
    if images_dir:
        files = []
        for e in IMG_EXTS:
            files += glob.glob(os.path.join(images_dir, "**", "*" + e), recursive=True)
        return sorted(files)
    # data.yaml 파싱 (의존성 없이 최소 파싱)
    import yaml  # pyyaml (ultralytics 의존성으로 설치돼 있음)
    with open(data_yaml) as f:
        d = yaml.safe_load(f)
    base = d.get("path", os.path.dirname(os.path.abspath(data_yaml)))
    val = d.get("val")
    if not val:
        raise SystemExit("data.yaml에 val: 항목이 없습니다")
    val_path = val if os.path.isabs(val) else os.path.join(base, val)
    if os.path.isfile(val_path):              # txt 리스트 파일
        lines = [l.strip() for l in open(val_path) if l.strip()]
        return [p if os.path.isabs(p) else os.path.join(base, p) for p in lines]
    files = []                                 # 디렉토리
    for e in IMG_EXTS:
        files += glob.glob(os.path.join(val_path, "**", "*" + e), recursive=True)
    return sorted(files)


def load_gt(label_path, w, h):
    """YOLO txt(cls cx cy bw bh, normalized) → [(cls, x1,y1,x2,y2 pixel), ...]"""
    boxes = []
    if os.path.exists(label_path):
        for ln in open(label_path):
            p = ln.split()
            if len(p) < 5:
                continue
            c = int(float(p[0]))
            cx, cy, bw, bh = map(float, p[1:5])
            boxes.append((c, (cx - bw / 2) * w, (cy - bh / 2) * h,
                          (cx + bw / 2) * w, (cy + bh / 2) * h))
    return boxes


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def average_precision(scores, tps, n_gt):
    """all-points AP (참고용). scores 내림차순으로 PR 곡선 적분."""
    if n_gt == 0 or not scores:
        return 0.0
    order = np.argsort(-np.array(scores))
    tp = np.array(tps)[order]
    fp = 1 - tp
    tp_c, fp_c = np.cumsum(tp), np.cumsum(fp)
    rec = tp_c / n_gt
    prec = tp_c / np.maximum(tp_c + fp_c, 1e-9)
    # precision envelope
    mrec = np.concatenate(([0.0], rec, [rec[-1]]))
    mpre = np.concatenate(([1.0], prec, [0.0]))
    for i in range(len(mpre) - 1, 0, -1):
        mpre[i - 1] = max(mpre[i - 1], mpre[i])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def main():
    ap = argparse.ArgumentParser(description="best.engine conf-threshold 스윕 평가")
    ap.add_argument("--engine", default="/home/jetson_dsm/polewatch/models/best.engine")
    ap.add_argument("--data", default=None, help="ultralytics data.yaml")
    ap.add_argument("--images", default=None, help="val 이미지 디렉토리")
    ap.add_argument("--labels", default=None, help="val 라벨 디렉토리(미지정 시 images→labels 치환)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--iou", type=float, default=0.5, help="TP 매칭 IoU 임계")
    ap.add_argument("--nms-iou", type=float, default=0.7, help="추론 NMS IoU")
    ap.add_argument("--conf-min", type=float, default=0.001, help="후보 수집용 최소 conf")
    ap.add_argument("--step", type=float, default=0.05, help="threshold 스윕 간격")
    ap.add_argument("--out", default="eval.csv")
    ap.add_argument("--plot", default="pr_curve.png")
    a = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(a.engine, task="detect")
    names = model.names
    classes = sorted(names.keys())

    imgs = list_val_images(a.data, a.images)
    if not imgs:
        raise SystemExit("val 이미지를 찾지 못했습니다 (--data 또는 --images 확인)")
    print(f"[eval] 이미지 {len(imgs)}장 · 클래스 {[names[c] for c in classes]} · "
          f"매칭 IoU {a.iou} · NMS IoU {a.nms_iou} · conf_min {a.conf_min}")

    # 클래스별 (score, is_tp) 누적 + GT 수
    per = {c: {"score": [], "tp": [], "gt": 0} for c in classes}
    for i, img in enumerate(imgs):
        lbl = a.labels and os.path.join(a.labels, os.path.splitext(os.path.basename(img))[0] + ".txt") \
            or labels_path_for(img)
        r = model.predict(img, conf=a.conf_min, iou=a.nms_iou, imgsz=a.imgsz, verbose=False)[0]
        h, w = r.orig_shape
        gt = load_gt(lbl, w, h)
        preds = [(float(b.conf), int(b.cls),
                  tuple(float(v) for v in b.xyxy[0])) for b in r.boxes]
        for c in classes:
            g = [gb[1:] for gb in gt if gb[0] == c]
            per[c]["gt"] += len(g)
            pc = sorted([(s, box) for s, cl, box in preds if cl == c], key=lambda x: -x[0])
            matched = [False] * len(g)
            for s, box in pc:
                best_i, best_j = a.iou, -1
                for j, gb in enumerate(g):
                    if matched[j]:
                        continue
                    v = iou(box, gb)
                    if v >= best_i:
                        best_i, best_j = v, j
                per[c]["score"].append(s)
                per[c]["tp"].append(1 if best_j >= 0 else 0)
                if best_j >= 0:
                    matched[best_j] = True
        if (i + 1) % 50 == 0:
            print(f"[eval] {i+1}/{len(imgs)}")

    thresholds = [round(x, 4) for x in np.arange(a.step, 1.0, a.step)]

    def metrics_at(d, t):
        tp = sum(1 for s, y in zip(d["score"], d["tp"]) if s >= t and y)
        fp = sum(1 for s, y in zip(d["score"], d["tp"]) if s >= t and not y)
        fn = d["gt"] - tp
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / d["gt"] if d["gt"] else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        return tp, fp, fn, p, r, f1

    # 전체(micro) = 모든 클래스 합
    alld = {"score": sum((per[c]["score"] for c in classes), []),
            "tp": sum((per[c]["tp"] for c in classes), []),
            "gt": sum(per[c]["gt"] for c in classes)}

    rows = []  # CSV
    blocks = [(f"class={names[c]}", per[c]) for c in classes] + [("ALL(micro)", alld)]
    for title, d in blocks:
        print(f"\n===== {title}  (GT={d['gt']}, AP={average_precision(d['score'], d['tp'], d['gt']):.4f}) =====")
        print(f"{'conf':>6} {'TP':>6} {'FP':>6} {'FN':>6} {'Prec':>7} {'Recall':>7} {'F1':>7}")
        for t in thresholds:
            tp, fp, fn, p, r, f1 = metrics_at(d, t)
            print(f"{t:6.2f} {tp:6d} {fp:6d} {fn:6d} {p:7.3f} {r:7.3f} {f1:7.3f}")
            rows.append([title, t, tp, fp, fn, round(p, 4), round(r, 4), round(f1, 4)])

    with open(a.out, "w") as f:
        f.write("group,conf,TP,FP,FN,precision,recall,f1\n")
        for row in rows:
            f.write(",".join(str(x) for x in row) + "\n")
    print(f"\n[eval] CSV 저장: {a.out}")

    # PR curve PNG (운용점 표시 없음)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(7, 6))
        for title, d in blocks:
            P, R = [], []
            for t in thresholds:
                _, _, _, p, r, _ = metrics_at(d, t)
                P.append(p); R.append(r)
            plt.plot(R, P, marker="o", ms=3, label=f"{title} (AP={average_precision(d['score'],d['tp'],d['gt']):.3f})")
        plt.xlabel("Recall"); plt.ylabel("Precision")
        plt.title("PR curve (conf sweep) — 운용점 미선택")
        plt.xlim(0, 1); plt.ylim(0, 1.02); plt.grid(True, alpha=0.3); plt.legend()
        plt.savefig(a.plot, dpi=120, bbox_inches="tight")
        print(f"[eval] PR curve 저장: {a.plot}")
    except Exception as e:
        print(f"[eval] PR curve PNG 생략({e}) — CSV로 플롯 가능")


if __name__ == "__main__":
    main()
