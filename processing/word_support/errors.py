"""Word 转换链路的统一错误类型。"""

# 错误类别（与 .project/plans/word-support/design.md 错误表对齐）
KIND_PRECHECK = "precheck"          # 前置校验拒绝（损坏/加密/非 docx）
KIND_ENGINE_MISSING = "engine_missing"
KIND_MANUAL_PATH_ONLY = "manual_path_only"
KIND_CANCELLED = "cancelled"
KIND_TIMEOUT = "timeout"
KIND_PERMISSION = "permission"      # macOS 自动化授权被拒
KIND_CONVERT = "convert"
KIND_INVALID_PDF = "invalid_pdf"
KIND_SOURCE_CHANGED = "source_changed"


class ConversionError(RuntimeError):
    """带机器可读类别的转换错误；message 为可直接展示的中文文案。"""

    def __init__(self, kind: str, message: str):
        self.kind = kind
        super().__init__(message)
