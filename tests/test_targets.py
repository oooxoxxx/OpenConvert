"""檔案類型判定與目標規劃。"""

from __future__ import annotations

from pathlib import Path

from openconvert.core.kinds import MediaKind, kinds_for, primary_kind
from openconvert.core.targets import (
    available_targets,
    plan_groups,
    preferred_target,
    target_by_token,
)


def test_kind_for_common_extensions():
    assert primary_kind("a.mp4") is MediaKind.VIDEO
    assert primary_kind("a.MKV") is MediaKind.VIDEO
    assert primary_kind("a.mp3") is MediaKind.AUDIO
    assert primary_kind("a.jpeg") is MediaKind.IMAGE
    assert primary_kind("a.pdf") is MediaKind.PDF
    assert primary_kind("a.epub") is MediaKind.EPUB
    assert primary_kind("a.cbz") is MediaKind.CBZ
    assert primary_kind("a.xyz") is MediaKind.UNKNOWN


def test_gif_is_both_image_and_video_source():
    kinds = kinds_for("anim.gif")
    assert kinds[0] is MediaKind.IMAGE
    assert MediaKind.VIDEO in kinds


def test_targets_for_single_image_include_common_formats():
    tokens = {spec.token for spec in available_targets([Path("photo.png")])}
    assert {"png", "jpg", "webp", "epub", "cbz", "img-pdf"} <= tokens
    assert "mp4" not in tokens


def test_pdf_merge_requires_two_files():
    one = {spec.token for spec in available_targets([Path("a.pdf")])}
    assert "pdf-merge" not in one

    two = {spec.token for spec in available_targets([Path("a.pdf"), Path("b.pdf")])}
    assert "pdf-merge" in two


def test_video_targets_include_audio_extraction():
    tokens = {spec.token for spec in available_targets([Path("clip.mp4")])}
    assert "mp4" in tokens
    assert "mp3" in tokens
    assert "png" not in tokens


def test_plan_groups_single_files_by_default():
    spec = target_by_token("jpg")
    assert spec is not None
    groups = plan_groups(spec, [Path("a.png"), Path("b.png")])
    assert len(groups) == 2


def test_plan_groups_merges_images_for_ebook():
    spec = target_by_token("epub")
    assert spec is not None
    groups = plan_groups(spec, [Path("a.png"), Path("b.png"), Path("c.png")])
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_plan_groups_keeps_non_group_files_separate():
    spec = target_by_token("epub")
    assert spec is not None
    groups = plan_groups(spec, [Path("a.png"), Path("book.cbz")])
    assert len(groups) == 2


def test_plan_groups_merges_pdfs():
    spec = target_by_token("pdf-merge")
    assert spec is not None
    groups = plan_groups(spec, [Path("a.pdf"), Path("b.pdf"), Path("c.pdf")])
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_preferred_target_uses_last_format_when_available():
    spec = preferred_target([Path("a.png")], "webp")
    assert spec is not None
    assert spec.token == "webp"


def test_preferred_target_falls_back_to_first():
    spec = preferred_target([Path("a.png")], "mp4")
    assert spec is not None
    assert spec.token != "mp4"


def test_available_targets_keep_declaration_order():
    tokens = [spec.token for spec in available_targets([Path("a.png")])]
    assert tokens[0] == "png"
    assert tokens.index("png") < tokens.index("jpg") < tokens.index("bmp")


def test_preferred_target_avoids_source_extension():
    assert preferred_target([Path("a.png")], None).token == "jpg"  # type: ignore[union-attr]
    assert preferred_target([Path("a.jpeg")], None).token == "png"  # type: ignore[union-attr]
    assert preferred_target([Path("a.mp4")], None).token == "mkv"  # type: ignore[union-attr]
