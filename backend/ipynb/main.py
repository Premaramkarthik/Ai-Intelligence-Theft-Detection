from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import time
from collections import Counter
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import numpy as np
import torch
from decord import VideoReader, cpu
from torch import nn
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForVideoClassification, AutoVideoProcessor
from transformers.models.vjepa2.video_processing_vjepa2 import VJEPA2VideoProcessor


LOG_FORMAT = "[%(levelname)-8s][%(asctime)s][%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOGGER = logging.getLogger("vjepa2-finetune")


@dataclass(frozen=True)
class VideoSample:
    path: Path
    label: int


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=DATE_FORMAT, force=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune a Hugging Face V-JEPA 2 video classifier.")
    parser.add_argument(
        "--model-id",
        type=str,
        default="facebook/vjepa2-vitl-fpc16-256-ssv2",
        help="Hugging Face repo id to fine-tune.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Dataset root. Expected class folders live under this directory.",
    )
    parser.add_argument(
        "--train-manifest",
        type=Path,
        default=Path("data/manifests/shoplifting_train.csv"),
        help="Training manifest with lines like /abs/path/video.mp4::label.",
    )
    parser.add_argument(
        "--val-manifest",
        type=Path,
        default=Path("data/manifests/shoplifting_val.csv"),
        help="Validation manifest with lines like /abs/path/video.mp4::label.",
    )
    parser.add_argument(
        "--label-map",
        type=Path,
        default=Path("data/manifests/label_map.json"),
        help="Optional JSON file containing label_map.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("hf_vjepa2_finetune"),
        help="Directory to store logs and checkpoints.",
    )
    parser.add_argument("--epochs", type=int, default=5, help="Number of fine-tuning epochs.")
    parser.add_argument("--batch-size", type=int, default=1, help="Mini-batch size.")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="AdamW learning rate.")
    parser.add_argument("--weight-decay", type=float, default=1e-2, help="AdamW weight decay.")
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader workers.")
    parser.add_argument("--seed", type=int, default=239, help="Random seed.")
    parser.add_argument(
        "--frames-per-clip",
        type=int,
        default=None,
        help="Frames sampled per video. Defaults to the model config value.",
    )
    parser.add_argument(
        "--max-train-samples",
        type=int,
        default=None,
        help="Optional cap on training samples for quick experiments.",
    )
    parser.add_argument(
        "--max-val-samples",
        type=int,
        default=None,
        help="Optional cap on validation samples for quick experiments.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=10,
        help="How often to log training progress, in optimizer steps.",
    )
    parser.add_argument(
        "--train-backbone",
        action="store_true",
        help="If set, fine-tune the full V-JEPA 2 backbone. By default only the pooler and classifier train.",
    )
    parser.add_argument(
        "--amp",
        action="store_true",
        help="Use float16 autocast on CUDA.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifests, video loading, and preprocessing without downloading weights or training.",
    )
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def infer_project_root() -> Path:
    return Path(__file__).resolve().parent


def normalize_video_path(raw_path: str, project_root: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.exists():
        return candidate.resolve()

    windows_parts = PureWindowsPath(raw_path).parts
    if "vjepa2" in windows_parts:
        repo_index = windows_parts.index("vjepa2")
        translated = project_root.joinpath(*windows_parts[repo_index + 1 :])
        if translated.exists():
            return translated.resolve()

    relative_candidate = (project_root / raw_path).resolve()
    if relative_candidate.exists():
        return relative_candidate

    return candidate


def parse_manifest(manifest_path: Path, project_root: Path) -> list[VideoSample]:
    samples: list[VideoSample] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_num, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if "::" in line:
                path_str, label_str = line.rsplit("::", 1)
            else:
                parts = line.rsplit(None, 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid manifest row at {manifest_path}:{line_num}: {raw_line.rstrip()}")
                path_str, label_str = parts
            label = int(label_str)
            path = normalize_video_path(path_str, project_root)
            samples.append(VideoSample(path=path, label=label))
    return samples


def infer_label_map(data_dir: Path) -> dict[str, int]:
    class_dirs = sorted(
        path.name for path in data_dir.iterdir() if path.is_dir() and path.name != "manifests"
    )
    if not class_dirs:
        raise FileNotFoundError(f"No class folders found in {data_dir}")
    return {name: idx for idx, name in enumerate(class_dirs)}


def load_label_mappings(label_map_path: Path, data_dir: Path) -> tuple[dict[str, int], dict[int, str]]:
    if label_map_path.exists():
        payload = json.loads(label_map_path.read_text(encoding="utf-8"))
        label2id = {str(k): int(v) for k, v in payload["label_map"].items()}
    else:
        label2id = infer_label_map(data_dir)
    id2label = {idx: label for label, idx in label2id.items()}
    return label2id, id2label


def build_samples_from_folders(
    data_dir: Path,
    label2id: dict[str, int],
    seed: int,
    val_ratio: float = 0.2,
) -> tuple[list[VideoSample], list[VideoSample]]:
    rng = random.Random(seed)
    train_samples: list[VideoSample] = []
    val_samples: list[VideoSample] = []
    for class_name, label in label2id.items():
        class_dir = data_dir / class_name
        if not class_dir.exists():
            raise FileNotFoundError(f"Expected class directory not found: {class_dir}")
        videos = sorted(
            path for path in class_dir.iterdir() if path.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv"}
        )
        if not videos:
            raise FileNotFoundError(f"No videos found in {class_dir}")
        if len(videos) == 1:
            sample = VideoSample(path=videos[0].resolve(), label=label)
            train_samples.append(sample)
            val_samples.append(sample)
            continue
        rng.shuffle(videos)
        split_index = max(1, int(len(videos) * (1.0 - val_ratio)))
        if split_index >= len(videos):
            split_index = len(videos) - 1
        train_samples.extend(VideoSample(path=path.resolve(), label=label) for path in videos[:split_index])
        val_samples.extend(VideoSample(path=path.resolve(), label=label) for path in videos[split_index:])
    return train_samples, val_samples


def resolve_dataset_splits(args: argparse.Namespace, project_root: Path) -> tuple[list[VideoSample], list[VideoSample], dict[str, int], dict[int, str]]:
    label2id, id2label = load_label_mappings(args.label_map, args.data_dir)

    if args.train_manifest.exists() and args.val_manifest.exists():
        train_samples = parse_manifest(args.train_manifest, project_root)
        val_samples = parse_manifest(args.val_manifest, project_root)
    else:
        train_samples, val_samples = build_samples_from_folders(args.data_dir, label2id, seed=args.seed)

    if args.max_train_samples is not None:
        train_samples = train_samples[: args.max_train_samples]
    if args.max_val_samples is not None:
        val_samples = val_samples[: args.max_val_samples]

    if not train_samples:
        raise ValueError("Training split is empty.")
    if not val_samples:
        raise ValueError("Validation split is empty.")

    return train_samples, val_samples, label2id, id2label


def sample_frame_indices(num_frames: int, frames_per_clip: int) -> np.ndarray:
    if num_frames <= 0:
        raise ValueError("Video contains no frames.")
    if num_frames >= frames_per_clip:
        return np.linspace(0, num_frames - 1, num=frames_per_clip, dtype=np.int64)
    indices = np.linspace(0, num_frames - 1, num=num_frames, dtype=np.int64)
    pad = np.full(frames_per_clip - num_frames, num_frames - 1, dtype=np.int64)
    return np.concatenate([indices, pad], axis=0)


class ManifestVideoDataset(Dataset):
    def __init__(
        self,
        samples: list[VideoSample],
        processor: AutoVideoProcessor | VJEPA2VideoProcessor,
        frames_per_clip: int,
        logger: logging.Logger,
    ) -> None:
        self.samples = samples
        self.processor = processor
        self.frames_per_clip = frames_per_clip
        self.logger = logger

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor | str]:
        for attempt in range(min(10, len(self.samples))):
            sample = self.samples[(index + attempt) % len(self.samples)]
            try:
                frames = self._read_video(sample.path)
                inputs = self.processor(frames, return_tensors="pt")
                pixel_values = inputs["pixel_values_videos"].squeeze(0)
                return {
                    "pixel_values_videos": pixel_values,
                    "labels": torch.tensor(sample.label, dtype=torch.long),
                    "path": str(sample.path),
                }
            except Exception as exc:
                self.logger.warning("Skipping unreadable video %s (%s)", sample.path, exc)
        raise RuntimeError("Failed to decode a valid video after multiple attempts.")

    def _read_video(self, path: Path) -> np.ndarray:
        if not path.exists():
            raise FileNotFoundError(path)
        reader = VideoReader(str(path), ctx=cpu(0))
        indices = sample_frame_indices(len(reader), self.frames_per_clip)
        frames = reader.get_batch(indices.tolist()).asnumpy()
        if frames.ndim != 4:
            raise ValueError(f"Unexpected frame tensor shape for {path}: {frames.shape}")
        if frames.shape[-1] == 1:
            frames = np.repeat(frames, 3, axis=-1)
        return frames


def collate_batch(batch: list[dict[str, torch.Tensor | str]]) -> dict[str, torch.Tensor | list[str]]:
    return {
        "pixel_values_videos": torch.stack([item["pixel_values_videos"] for item in batch]),
        "labels": torch.stack([item["labels"] for item in batch]),
        "paths": [item["path"] for item in batch],
    }


def count_parameters(module: nn.Module) -> tuple[int, int]:
    total = sum(parameter.numel() for parameter in module.parameters())
    trainable = sum(parameter.numel() for parameter in module.parameters() if parameter.requires_grad)
    return total, trainable


def freeze_for_head_only_finetuning(model: nn.Module) -> None:
    for parameter in model.parameters():
        parameter.requires_grad = False
    for parameter in model.pooler.parameters():
        parameter.requires_grad = True
    for parameter in model.classifier.parameters():
        parameter.requires_grad = True


def log_parameter_summary(model: nn.Module) -> dict[str, dict[str, int]]:
    summary = {
        "model": {},
        "backbone": {},
        "pooler": {},
        "classifier": {},
    }
    summary["model"]["total"], summary["model"]["trainable"] = count_parameters(model)
    summary["backbone"]["total"], summary["backbone"]["trainable"] = count_parameters(model.vjepa2)
    summary["pooler"]["total"], summary["pooler"]["trainable"] = count_parameters(model.pooler)
    summary["classifier"]["total"], summary["classifier"]["trainable"] = count_parameters(model.classifier)

    LOGGER.info("Total parameters: %s", f"{summary['model']['total']:,}")
    LOGGER.info("Trainable parameters: %s", f"{summary['model']['trainable']:,}")
    LOGGER.info(
        "Backbone trainable parameters: %s / %s",
        f"{summary['backbone']['trainable']:,}",
        f"{summary['backbone']['total']:,}",
    )
    LOGGER.info(
        "Pooler trainable parameters: %s / %s",
        f"{summary['pooler']['trainable']:,}",
        f"{summary['pooler']['total']:,}",
    )
    LOGGER.info(
        "Classifier trainable parameters: %s / %s",
        f"{summary['classifier']['trainable']:,}",
        f"{summary['classifier']['total']:,}",
    )
    return summary


def build_optimizer(model: nn.Module, learning_rate: float, weight_decay: float) -> torch.optim.Optimizer:
    trainable_parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    if not trainable_parameters:
        raise ValueError("No trainable parameters found. Enable --train-backbone or unfreeze a head.")
    return torch.optim.AdamW(trainable_parameters, lr=learning_rate, weight_decay=weight_decay)


def compute_accuracy(logits: torch.Tensor, labels: torch.Tensor) -> float:
    predictions = logits.argmax(dim=-1)
    return (predictions == labels).float().mean().item()


def run_epoch(
    model: nn.Module,
    data_loader: DataLoader,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    amp: bool,
    epoch_index: int,
    log_every: int,
) -> tuple[float, float]:
    is_training = optimizer is not None
    model.train(is_training)
    total_loss = 0.0
    total_correct = 0
    total_examples = 0
    start_time = time.time()

    for step, batch in enumerate(data_loader, start=1):
        pixel_values = batch["pixel_values_videos"].to(device)
        labels = batch["labels"].to(device)

        autocast_context = (
            torch.autocast(device_type="cuda", dtype=torch.float16) if amp and device.type == "cuda" else nullcontext()
        )

        with autocast_context:
            outputs = model(pixel_values_videos=pixel_values, labels=labels)
            loss = outputs.loss
            logits = outputs.logits

        if is_training:
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()

        batch_size = labels.size(0)
        total_examples += batch_size
        total_loss += loss.item() * batch_size
        total_correct += int((logits.argmax(dim=-1) == labels).sum().item())

        if step % log_every == 0 or step == len(data_loader):
            elapsed = time.time() - start_time
            avg_loss = total_loss / max(total_examples, 1)
            avg_acc = total_correct / max(total_examples, 1)
            phase = "train" if is_training else "val"
            LOGGER.info(
                "epoch=%d phase=%s step=%d/%d avg_loss=%.4f avg_acc=%.4f elapsed=%.1fs",
                epoch_index + 1,
                phase,
                step,
                len(data_loader),
                avg_loss,
                avg_acc,
                elapsed,
            )

    return total_loss / max(total_examples, 1), total_correct / max(total_examples, 1)


def save_metrics_row(csv_path: Path, row: dict[str, float | int]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def save_checkpoint_bundle(
    output_dir: Path,
    tag: str,
    model: nn.Module,
    processor: AutoVideoProcessor,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    metrics: dict[str, float],
    summary: dict[str, dict[str, int]],
    label2id: dict[str, int],
    id2label: dict[int, str],
) -> None:
    target_dir = output_dir / tag
    target_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(target_dir)
    processor.save_pretrained(target_dir)
    payload = {
        "epoch": epoch,
        "metrics": metrics,
        "parameter_summary": summary,
        "label2id": label2id,
        "id2label": {str(key): value for key, value in id2label.items()},
        "optimizer": optimizer.state_dict(),
    }
    torch.save(payload, target_dir / "training_state.pt")


def log_dataset_summary(train_samples: list[VideoSample], val_samples: list[VideoSample], id2label: dict[int, str]) -> None:
    train_counts = Counter(sample.label for sample in train_samples)
    val_counts = Counter(sample.label for sample in val_samples)
    LOGGER.info("Training samples: %d", len(train_samples))
    LOGGER.info("Validation samples: %d", len(val_samples))
    LOGGER.info("Class mapping: %s", {label: idx for idx, label in id2label.items()})
    LOGGER.info(
        "Training distribution: %s",
        {id2label[label]: train_counts.get(label, 0) for label in sorted(id2label)},
    )
    LOGGER.info(
        "Validation distribution: %s",
        {id2label[label]: val_counts.get(label, 0) for label in sorted(id2label)},
    )


def build_data_loader(
    samples: list[VideoSample],
    processor: AutoVideoProcessor | VJEPA2VideoProcessor,
    frames_per_clip: int,
    batch_size: int,
    num_workers: int,
    shuffle: bool,
) -> DataLoader:
    dataset = ManifestVideoDataset(samples=samples, processor=processor, frames_per_clip=frames_per_clip, logger=LOGGER)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
        collate_fn=collate_batch,
    )


def try_first_batch(data_loader: DataLoader) -> None:
    batch = next(iter(data_loader))
    LOGGER.info("Dry run batch tensor shape: %s", tuple(batch["pixel_values_videos"].shape))
    LOGGER.info("Dry run labels shape: %s", tuple(batch["labels"].shape))
    LOGGER.info("Dry run sample paths: %s", batch["paths"][:2])


def load_processor(model_id: str, dry_run: bool) -> AutoVideoProcessor | VJEPA2VideoProcessor:
    if dry_run:
        return VJEPA2VideoProcessor()
    try:
        return AutoVideoProcessor.from_pretrained(model_id)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load processor for {model_id}. Make sure the model exists and you have internet access."
        ) from exc


def load_model(
    model_id: str,
    num_labels: int,
    label2id: dict[str, int],
    id2label: dict[int, str],
    device: torch.device,
) -> nn.Module:
    try:
        model = AutoModelForVideoClassification.from_pretrained(
            model_id,
            num_labels=num_labels,
            label2id=label2id,
            id2label=id2label,
            ignore_mismatched_sizes=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load model weights for {model_id}. Make sure the model exists and you have internet access."
        ) from exc
    return model.to(device)


def main() -> None:
    configure_logging()
    args = parse_args()
    project_root = infer_project_root()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    set_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    LOGGER.info("Device: %s", device)
    if device.type == "cpu":
        LOGGER.info("CPU mode is supported, but full fine-tuning will be slow.")

    train_samples, val_samples, label2id, id2label = resolve_dataset_splits(args, project_root)
    log_dataset_summary(train_samples, val_samples, id2label)

    processor = load_processor(args.model_id, dry_run=args.dry_run)
    frames_per_clip = args.frames_per_clip or 16
    train_loader = build_data_loader(
        samples=train_samples,
        processor=processor,
        frames_per_clip=frames_per_clip,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        shuffle=True,
    )
    val_loader = build_data_loader(
        samples=val_samples,
        processor=processor,
        frames_per_clip=frames_per_clip,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        shuffle=False,
    )

    if args.dry_run:
        LOGGER.info("Dry run enabled. Validating manifests, decoding, and preprocessing only.")
        try_first_batch(train_loader)
        return

    model = load_model(
        model_id=args.model_id,
        num_labels=len(label2id),
        label2id=label2id,
        id2label=id2label,
        device=device,
    )
    if args.frames_per_clip is None and hasattr(model.config, "frames_per_clip"):
        frames_per_clip = int(model.config.frames_per_clip)
        LOGGER.info("Using frames_per_clip from model config: %d", frames_per_clip)
        train_loader = build_data_loader(
            samples=train_samples,
            processor=processor,
            frames_per_clip=frames_per_clip,
            batch_size=args.batch_size,
            num_workers=args.num_workers,
            shuffle=True,
        )
        val_loader = build_data_loader(
            samples=val_samples,
            processor=processor,
            frames_per_clip=frames_per_clip,
            batch_size=args.batch_size,
            num_workers=args.num_workers,
            shuffle=False,
        )

    if not args.train_backbone:
        freeze_for_head_only_finetuning(model)
        LOGGER.info("Backbone frozen. Training pooler + classifier only.")
    else:
        LOGGER.info("Full fine-tuning enabled.")

    summary = log_parameter_summary(model)
    optimizer = build_optimizer(model, learning_rate=args.learning_rate, weight_decay=args.weight_decay)

    run_config = {
        "model_id": args.model_id,
        "data_dir": str(args.data_dir.resolve()),
        "train_manifest": str(args.train_manifest.resolve()),
        "val_manifest": str(args.val_manifest.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "frames_per_clip": frames_per_clip,
        "device": str(device),
        "train_backbone": args.train_backbone,
        "parameter_summary": summary,
        "label2id": label2id,
        "id2label": {str(key): value for key, value in id2label.items()},
    }
    (args.output_dir / "run_config.json").write_text(json.dumps(run_config, indent=2), encoding="utf-8")

    metrics_path = args.output_dir / "metrics.csv"
    best_val_accuracy = float("-inf")

    for epoch in range(args.epochs):
        LOGGER.info("Starting epoch %d/%d", epoch + 1, args.epochs)
        train_loss, train_acc = run_epoch(
            model=model,
            data_loader=train_loader,
            optimizer=optimizer,
            device=device,
            amp=args.amp,
            epoch_index=epoch,
            log_every=args.log_every,
        )
        with torch.no_grad():
            val_loss, val_acc = run_epoch(
                model=model,
                data_loader=val_loader,
                optimizer=None,
                device=device,
                amp=False,
                epoch_index=epoch,
                log_every=args.log_every,
            )

        row = {
            "epoch": epoch + 1,
            "train_loss": train_loss,
            "train_acc": train_acc,
            "val_loss": val_loss,
            "val_acc": val_acc,
        }
        save_metrics_row(metrics_path, row)
        LOGGER.info(
            "Epoch %d complete: train_loss=%.4f train_acc=%.4f val_loss=%.4f val_acc=%.4f",
            epoch + 1,
            train_loss,
            train_acc,
            val_loss,
            val_acc,
        )

        save_checkpoint_bundle(
            output_dir=args.output_dir,
            tag="last",
            model=model,
            processor=processor,
            optimizer=optimizer,
            epoch=epoch + 1,
            metrics={"train_loss": train_loss, "train_acc": train_acc, "val_loss": val_loss, "val_acc": val_acc},
            summary=summary,
            label2id=label2id,
            id2label=id2label,
        )

        if val_acc > best_val_accuracy:
            best_val_accuracy = val_acc
            save_checkpoint_bundle(
                output_dir=args.output_dir,
                tag="best",
                model=model,
                processor=processor,
                optimizer=optimizer,
                epoch=epoch + 1,
                metrics={"train_loss": train_loss, "train_acc": train_acc, "val_loss": val_loss, "val_acc": val_acc},
                summary=summary,
                label2id=label2id,
                id2label=id2label,
            )
            LOGGER.info("Saved new best checkpoint with val_acc=%.4f", val_acc)

    LOGGER.info("Training complete. Best validation accuracy: %.4f", best_val_accuracy)


if __name__ == "__main__":
    main()
