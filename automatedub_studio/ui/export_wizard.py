"""Export wizard for configuring render output."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from automatedub.config import ToolConfig
from automatedub_studio.backend.export_service import (
    ExportEncoderCapabilities,
    build_mux_command,
)
from automatedub_studio.export.manager import (
    AudioMode,
    ExportCapabilityReport,
    ExportConfiguration,
    SubtitleMode,
    VideoEncodingPreset,
    detect_export_encoder_capabilities,
    inspect_export_capabilities,
    validate_export_presets,
)
from automatedub_studio.project.models import Project
from automatedub_studio.timeline.timeline_clip import Timeline

_SETTINGS_PREFIX = "export/"

_PRESET_DETAILS = {
    VideoEncodingPreset.FASTEST: {
        "label": "Copy Original",
        "description": (
            "Fastest export. Keeps the original video unchanged. Best when only "
            "audio or subtitles changed."
        ),
        "codec": "Original",
        "speed": "Fastest",
        "compatibility": "Source dependent",
        "size": "Same as source video plus rendered audio",
    },
    VideoEncodingPreset.COMPATIBLE_H264: {
        "label": "H.264 ⭐ Recommended",
        "description": (
            "Re-encodes the video into H.264 for maximum compatibility across "
            "Windows, macOS, phones, TVs, and web platforms."
        ),
        "codec": "H.264",
        "speed": "Medium",
        "compatibility": "Excellent",
        "size": "Medium",
    },
    VideoEncodingPreset.HIGH_COMPRESSION_H265: {
        "label": "H.265 (HEVC)",
        "description": (
            "Re-encodes to H.265 for a smaller, playable MP4. Slower export. "
            "Some older devices may not support playback."
        ),
        "codec": "H.265",
        "speed": "Slow",
        "compatibility": "Good on newer devices",
        "size": "Small",
    },
    VideoEncodingPreset.ORIGINAL_CODEC: {
        "label": "Original Codec (Advanced)",
        "description": (
            "Keeps the original codec (AV1, VP9, etc.). Best quality preservation "
            "but compatibility depends on the source format."
        ),
        "codec": "Original",
        "speed": "Fast",
        "compatibility": "Source dependent",
        "size": "Same as source video plus rendered audio",
    },
}


class ExportWizard(QDialog):
    def __init__(
        self,
        default_output_folder: Path,
        default_filename: str,
        settings: QSettings | None = None,
        project: Project | None = None,
        timeline: Timeline | None = None,
        tool_config: ToolConfig | None = None,
        encoder_capabilities: ExportEncoderCapabilities | None = None,
        capability_report: ExportCapabilityReport | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._capability_report = capability_report or (
            inspect_export_capabilities(project, timeline, tool_config)
            if tool_config is not None
            else None
        )
        self._encoder_capabilities = encoder_capabilities or (
            ExportEncoderCapabilities(
                self._capability_report.system.h264_encoder,
                self._capability_report.system.h265_encoder,
            )
            if self._capability_report is not None
            else None
        ) or (
            detect_export_encoder_capabilities(tool_config) if tool_config is not None else None
        )
        self._preset_validations = validate_export_presets(
            project,
            timeline,
            self._encoder_capabilities,
            self._capability_report,
        )
        self._preset_buttons: dict[VideoEncodingPreset, QRadioButton] = {}
        self._preset_descriptions: dict[VideoEncodingPreset, QLabel] = {}
        self.setWindowTitle("Export Video")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        remembered_folder = self._setting_value("output_folder", str(default_output_folder))
        self.output_folder_edit = QLineEdit(remembered_folder)
        self.output_folder_edit.setObjectName("export_output_folder_edit")
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.output_folder_edit)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_output_folder)
        folder_row.addWidget(browse)
        form.addRow("Output Folder", folder_row)

        self.filename_edit = QLineEdit(default_filename)
        self.filename_edit.setObjectName("export_filename_edit")
        form.addRow("Filename", self.filename_edit)

        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        preset_layout = QVBoxLayout()
        for preset in VideoEncodingPreset:
            details = _PRESET_DETAILS[preset]
            button = QRadioButton(str(details["label"]))
            button.setObjectName(f"export_preset_{preset.value}")
            button.setToolTip(str(details["description"]))
            self.preset_group.addButton(button)
            self.preset_group.setId(button, list(VideoEncodingPreset).index(preset))
            preset_layout.addWidget(button)
            self._preset_buttons[preset] = button
            description = QLabel(str(details["description"]))
            description.setWordWrap(True)
            description.setObjectName(f"export_preset_{preset.value}_description")
            preset_layout.addWidget(description)
            self._preset_descriptions[preset] = description
        form.addRow("Video Encoding", preset_layout)
        self.validation_label = QLabel()
        self.validation_label.setObjectName("export_preset_validation_message")
        self.validation_label.setWordWrap(True)
        form.addRow("Why is this unavailable?", self.validation_label)

        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("export_quality_combo")
        self.quality_combo.addItems(["Highest Quality", "High", "Balanced ⭐", "Small File"])
        form.addRow("Compression Quality", self.quality_combo)

        self.codec_label = QLabel()
        self.codec_label.setObjectName("export_estimate_codec")
        self.size_label = QLabel()
        self.size_label.setObjectName("export_estimate_file_size")
        self.speed_label = QLabel()
        self.speed_label.setObjectName("export_estimate_speed")
        self.compatibility_label = QLabel()
        self.compatibility_label.setObjectName("export_estimate_compatibility")
        self.audio_codec_label = QLabel("AAC")
        self.audio_codec_label.setObjectName("export_estimate_audio_codec")
        self.subtitle_preview_label = QLabel()
        self.subtitle_preview_label.setObjectName("export_estimate_subtitle_mode")
        form.addRow("Export Preview", QLabel())
        form.addRow("Video Codec", self.codec_label)
        form.addRow("Audio Codec", self.audio_codec_label)
        form.addRow("Subtitle Mode", self.subtitle_preview_label)
        form.addRow("Estimated File Size", self.size_label)
        form.addRow("Estimated Export Speed", self.speed_label)
        form.addRow("Compatibility", self.compatibility_label)

        self.audio_mode_combo = QComboBox()
        self.audio_mode_combo.setObjectName("export_audio_mode_combo")
        self.audio_mode_combo.addItem("Khmer only", AudioMode.KHMER_ONLY.value)
        self.audio_mode_combo.addItem("Original only", AudioMode.ORIGINAL_ONLY.value)
        self.audio_mode_combo.addItem("Mixed", AudioMode.MIXED.value)
        self.audio_mode_combo.setCurrentIndex(2)
        form.addRow("Audio Mode", self.audio_mode_combo)

        self.subtitle_mode_combo = QComboBox()
        self.subtitle_mode_combo.setObjectName("export_subtitle_mode_combo")
        self.subtitle_mode_combo.addItem("None", SubtitleMode.NONE.value)
        self.subtitle_mode_combo.addItem("External (.srt)", SubtitleMode.EXTERNAL_SRT.value)
        self.subtitle_mode_combo.addItem("Embedded", SubtitleMode.EMBEDDED.value)
        self.subtitle_mode_combo.addItem("Burned Into Video", SubtitleMode.BURNED_IN.value)
        form.addRow("Subtitle Mode", self.subtitle_mode_combo)
        self.subtitle_description = QLabel()
        self.subtitle_description.setObjectName("export_subtitle_mode_description")
        self.subtitle_description.setWordWrap(True)
        form.addRow("", self.subtitle_description)

        self.diagnostics_group = QGroupBox("Export Diagnostics")
        self.diagnostics_group.setObjectName("export_diagnostics_panel")
        diagnostics_form = QFormLayout(self.diagnostics_group)
        self.diagnostics_source_label = QLabel()
        self.diagnostics_system_label = QLabel()
        self.diagnostics_presets_label = QLabel()
        self.diagnostics_selected_label = QLabel()
        self.diagnostics_command_label = QLabel()
        self.diagnostics_command_label.setWordWrap(True)
        for label in (
            self.diagnostics_source_label,
            self.diagnostics_system_label,
            self.diagnostics_presets_label,
            self.diagnostics_selected_label,
            self.diagnostics_command_label,
        ):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        diagnostics_form.addRow("Source Video", self.diagnostics_source_label)
        diagnostics_form.addRow("System", self.diagnostics_system_label)
        diagnostics_form.addRow("Available Export Presets", self.diagnostics_presets_label)
        diagnostics_form.addRow("Selected Preset", self.diagnostics_selected_label)
        diagnostics_form.addRow("Final FFmpeg Command", self.diagnostics_command_label)

        self._apply_preset_validations()
        self._restore_settings()
        self._ensure_selected_preset_available()
        self.preset_group.buttonClicked.connect(lambda *_: self._update_estimates())
        self.quality_combo.currentTextChanged.connect(lambda *_: self._update_estimates())
        self.subtitle_mode_combo.currentIndexChanged.connect(lambda *_: self._update_estimates())
        self.filename_edit.textChanged.connect(lambda *_: self._update_estimates())
        self._update_estimates()

        layout.addLayout(form)
        layout.addWidget(self.diagnostics_group)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.export_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.export_button.setObjectName("export_confirm_button")
        self._update_estimates()
        layout.addWidget(buttons)

    def configuration(self) -> ExportConfiguration:
        config = ExportConfiguration(
            output_folder=Path(self.output_folder_edit.text()).expanduser(),
            filename=self.filename_edit.text().strip(),
            video_quality=self._selected_quality(),
            codec=self._codec_for_preset(self._selected_preset()),
            video_preset=self._selected_preset(),
            audio_mode=AudioMode(str(self.audio_mode_combo.currentData())),
            subtitle_mode=SubtitleMode(str(self.subtitle_mode_combo.currentData())),
        )
        self._save_settings(config)
        return config

    def _browse_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose Export Folder")
        if folder:
            self.output_folder_edit.setText(folder)

    def _selected_preset(self) -> VideoEncodingPreset:
        checked = self.preset_group.checkedButton()
        if checked is None:
            return VideoEncodingPreset.COMPATIBLE_H264
        for preset in VideoEncodingPreset:
            if checked.objectName() == f"export_preset_{preset.value}":
                return preset
        return VideoEncodingPreset.COMPATIBLE_H264

    def _selected_quality(self) -> str:
        return self.quality_combo.currentText().replace(" ⭐", "")

    @staticmethod
    def _codec_for_preset(preset: VideoEncodingPreset) -> str:
        if preset == VideoEncodingPreset.HIGH_COMPRESSION_H265:
            return "h265"
        if preset == VideoEncodingPreset.ORIGINAL_CODEC:
            return "original"
        if preset == VideoEncodingPreset.FASTEST:
            return "copy"
        return "h264"

    def _restore_settings(self) -> None:
        preset = self._setting_value(
            "video_preset",
            VideoEncodingPreset.COMPATIBLE_H264.value,
        )
        for button in self.preset_group.buttons():
            if button.objectName() == f"export_preset_{preset}":
                button.setChecked(True)
                break
        if self.preset_group.checkedButton() is None:
            compatible = self.findChild(
                QRadioButton, f"export_preset_{VideoEncodingPreset.COMPATIBLE_H264.value}"
            )
            if compatible is not None:
                compatible.setChecked(True)

        self._set_combo_value(
            self.quality_combo,
            self._quality_label(self._setting_value("video_quality", "Balanced")),
        )
        self._set_combo_data(
            self.audio_mode_combo,
            self._setting_value("audio_mode", AudioMode.MIXED.value),
        )
        self._set_combo_data(
            self.subtitle_mode_combo,
            self._setting_value("subtitle_mode", SubtitleMode.NONE.value),
        )

    def _apply_preset_validations(self) -> None:
        unavailable: list[str] = []
        warnings: list[str] = []
        for preset, validation in self._preset_validations.items():
            button = self._preset_buttons[preset]
            description = self._preset_descriptions[preset]
            details = _PRESET_DETAILS[preset]
            button.setEnabled(validation.available)
            description_text = str(details["description"])
            if validation.available:
                button.setToolTip(validation.warning or validation.message)
                description_text += f"\n\nAvailable: {validation.message}"
                if validation.warning:
                    description_text += f"\n\nWarning: {validation.warning}"
                    warnings.append(f"{details['label']}: {validation.warning}")
            else:
                button.setToolTip(validation.message)
                status = (
                    "Coming Soon"
                    if validation.message.startswith("Coming Soon.")
                    else "Unavailable"
                )
                description_text += f"\n\n{status}\n{validation.message}"
                unavailable.append(f"{details['label']}: {validation.message}")
            description.setText(description_text)
        messages = unavailable + warnings
        self.validation_label.setText(
            "\n".join(messages) if messages else "All export presets are available."
        )

    def refresh_capabilities(self) -> None:
        """Re-evaluate presets after source media or system support changes."""
        if self._capability_report is None:
            return
        self._preset_validations = validate_export_presets(
            None,
            encoder_capabilities=ExportEncoderCapabilities(
                self._capability_report.system.h264_encoder,
                self._capability_report.system.h265_encoder,
            ),
            capability_report=self._capability_report,
        )
        self._apply_preset_validations()
        self._ensure_selected_preset_available()
        self._update_estimates()

    def _ensure_selected_preset_available(self) -> None:
        selected = self._selected_preset()
        if self._preset_validations[selected].available:
            return
        self._preset_buttons[VideoEncodingPreset.COMPATIBLE_H264].setChecked(True)

    def _save_settings(self, config: ExportConfiguration) -> None:
        if self._settings is None:
            return
        self._settings.setValue(_SETTINGS_PREFIX + "output_folder", str(config.output_folder))
        self._settings.setValue(_SETTINGS_PREFIX + "video_preset", config.video_preset.value)
        self._settings.setValue(_SETTINGS_PREFIX + "video_quality", config.video_quality)
        self._settings.setValue(_SETTINGS_PREFIX + "audio_mode", config.audio_mode.value)
        self._settings.setValue(_SETTINGS_PREFIX + "subtitle_mode", config.subtitle_mode.value)

    def _setting_value(self, key: str, default: str) -> str:
        if self._settings is None:
            return default
        value = self._settings.value(_SETTINGS_PREFIX + key, default)
        return str(value) if value is not None else default

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _quality_label(value: str) -> str:
        if value == "Balanced":
            return "Balanced ⭐"
        return value

    def _update_estimates(self) -> None:
        preset = self._selected_preset()
        details = _PRESET_DETAILS[preset]
        quality = self._selected_quality()
        self.codec_label.setText(str(details["codec"]))
        self.speed_label.setText(str(details["speed"]))
        self.compatibility_label.setText(str(details["compatibility"]))
        self.size_label.setText(self._size_estimate(preset, quality))
        self.subtitle_preview_label.setText(self.subtitle_mode_combo.currentText())
        self.subtitle_description.setText(self._subtitle_description())
        reencoding = preset in (
            VideoEncodingPreset.COMPATIBLE_H264,
            VideoEncodingPreset.HIGH_COMPRESSION_H265,
        )
        self.quality_combo.setEnabled(reencoding)
        validation = self._preset_validations[preset]
        subtitle_requires_reencode = (
            self.subtitle_mode_combo.currentData() == SubtitleMode.BURNED_IN.value
        )
        valid = validation.available and not (
            subtitle_requires_reencode
            and preset in (VideoEncodingPreset.FASTEST, VideoEncodingPreset.ORIGINAL_CODEC)
        )
        if hasattr(self, "export_button"):
            self.export_button.setEnabled(valid)
        if not valid and subtitle_requires_reencode:
            self.validation_label.setText(
                "Burned Into Video requires re-encoding. Select H.264 or H.265."
            )
        self._update_diagnostics(preset)

    def _update_diagnostics(self, preset: VideoEncodingPreset) -> None:
        report = self._capability_report
        if report is None:
            self.diagnostics_source_label.setText("Source inspection is unavailable.")
            self.diagnostics_system_label.setText("FFmpeg capability inspection is unavailable.")
            self.diagnostics_presets_label.setText(self._preset_availability_text())
            self.diagnostics_selected_label.setText(self._preset_diagnostic_text(preset, None))
            self.diagnostics_command_label.setText("Available after a project is selected.")
            return
        codec = report.source_codec.upper() if report.source_codec else "Unknown"
        self.diagnostics_source_label.setText(
            f"Codec: {codec}\nContainer: {report.source_container.upper() or 'Unknown'}\n"
            f"Resolution: {report.source_resolution}\nFPS: {report.source_frame_rate}\n"
            f"Pixel format: {report.source_pixel_format}\n"
            f"Video edits: {'Yes' if report.has_video_edits else 'No'}\n"
            f"Audio edits: {'Yes' if report.has_audio_edits else 'No'}"
        )
        tracked_encoders = (
            "libx264",
            "libx265",
            "h264_videotoolbox",
            "hevc_videotoolbox",
            "libsvtav1",
        )
        available = report.system.available_encoders
        encoder_lines = [
            f"{name}: {'available' if name in available else 'unavailable'}"
            for name in tracked_encoders
        ]
        muxer_status = "available" if report.system.supports_mp4_muxing else "unavailable"
        encoder_lines.append(f"MP4 muxer: {muxer_status}")
        self.diagnostics_system_label.setText(
            f"{report.system.ffmpeg_version}\n" + "\n".join(encoder_lines)
        )
        self.diagnostics_presets_label.setText(self._preset_availability_text())
        self.diagnostics_selected_label.setText(self._preset_diagnostic_text(preset, report))
        self.diagnostics_command_label.setText(self._planned_command(preset, report))

    def _preset_diagnostic_text(self, preset, report) -> str:
        validation = self._preset_validations[preset]
        required = {
            VideoEncodingPreset.FASTEST: "Required encoder: stream copy",
            VideoEncodingPreset.COMPATIBLE_H264: "Required encoder: H.264",
            VideoEncodingPreset.HIGH_COMPRESSION_H265: "Required encoder: H.265/HEVC",
            VideoEncodingPreset.ORIGINAL_CODEC: "Required encoder: stream copy",
        }[preset]
        actual = "Actual encoder: unavailable"
        if preset in (VideoEncodingPreset.FASTEST, VideoEncodingPreset.ORIGINAL_CODEC):
            actual = "Actual encoder: copy"
        elif report is not None:
            encoder = (
                report.system.h264_encoder
                if preset == VideoEncodingPreset.COMPATIBLE_H264
                else report.system.h265_encoder
            )
            actual = f"Actual encoder: {encoder or 'unavailable'}"
        status = "Supported" if validation.available else f"Unavailable: {validation.message}"
        quality = self._selected_quality()
        target = "copy"
        if report is not None:
            command = self._planned_command(preset, report).split()
            for flag in ("-crf", "-b:v"):
                if flag in command:
                    target = f"{flag} {command[command.index(flag) + 1]}"
                    break
        return f"{status}\n{required}\n{actual}\nSelected quality: {quality}\nTarget: {target}"

    def _preset_availability_text(self) -> str:
        return "\n".join(
            f"{_PRESET_DETAILS[preset]['label']}: "
            f"{'Available' if validation.available else 'Unavailable'}"
            f" - {validation.message}"
            for preset, validation in self._preset_validations.items()
        )

    def _planned_command(self, preset, report) -> str:
        if report.source_video is None:
            return "Unavailable: source video is required."
        encoder = "copy"
        if preset == VideoEncodingPreset.COMPATIBLE_H264:
            encoder = report.system.h264_encoder or "unavailable"
        elif preset == VideoEncodingPreset.HIGH_COMPRESSION_H265:
            encoder = report.system.h265_encoder or "unavailable"
        if encoder == "unavailable":
            return "Unavailable: required encoder was not detected."
        command = build_mux_command(
            "ffmpeg",
            report.source_video,
            Path(self.output_folder_edit.text()) / "mixed_audio.wav",
            Path(self.output_folder_edit.text()) / f"{self.filename_edit.text() or 'export'}.mp4",
            video_encoder=encoder,
            video_quality=self._selected_quality(),
        )
        return " ".join(str(part) for part in command)

    def _subtitle_description(self) -> str:
        mode = SubtitleMode(str(self.subtitle_mode_combo.currentData()))
        return {
            SubtitleMode.NONE: "No subtitles.",
            SubtitleMode.EXTERNAL_SRT: (
                "Creates a separate subtitle file. Good for editing; keep both files together."
            ),
            SubtitleMode.EMBEDDED: (
                "Stores subtitles inside the MP4 and can usually be turned on or off."
            ),
            SubtitleMode.BURNED_IN: "Subtitles become part of the video and cannot be disabled.",
        }[mode]

    @staticmethod
    def _size_estimate(preset: VideoEncodingPreset, quality: str) -> str:
        if preset in (VideoEncodingPreset.FASTEST, VideoEncodingPreset.ORIGINAL_CODEC):
            return "Same as source video plus rendered audio"
        if preset == VideoEncodingPreset.HIGH_COMPRESSION_H265:
            return {
                "Highest Quality": "Medium-small",
                "High": "Small",
                "Balanced": "Smaller",
                "Small File": "Smallest",
            }.get(quality, "Smaller")
        return {
            "Highest Quality": "Large",
            "High": "Medium-large",
            "Balanced": "Medium",
            "Small File": "Small",
        }.get(quality, "Medium")
