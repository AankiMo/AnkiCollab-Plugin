import os

from dataclasses import dataclass, field
from functional import seq
from typing import Any, Iterable, Set

from anki.utils import point_version

from .file_provider import FileProvider

ANKI_VERSION_23_10_00 = 231000


@dataclass
class NoteModelFileProvider(FileProvider):
    anki_collection: Any
    model_ids: Iterable[int]
    models: Iterable = field(init=False)

    def __post_init__(self):
        self.models = (
            seq(self.model_ids)
            .map(self.anki_collection.models.get)
            .filter(lambda m: m is not None)
            .to_list()
        )

    def get_files(self) -> Set[str]:
        media_dir = self.anki_collection.media.dir()
        existing_files = set(os.listdir(media_dir))
        referenced = self._referenced_static_media()
        return {
            file_name
            for file_name in referenced
            if file_name.startswith("_") and file_name in existing_files
        }

    def _referenced_static_media(self) -> Set[str]:
        if point_version() >= ANKI_VERSION_23_10_00:
            extract = self.anki_collection.media.extract_static_media_files
            return {name for model in self.models for name in extract(int(model["id"]))}
        return {
            file_name
            for file_name in os.listdir(self.anki_collection.media.dir())
            if file_name.startswith("_") and self.belongs_to_any_model(file_name)
        }

    def belongs_to_any_model(self, file_name: str) -> bool:
        return any(_model_references(model, file_name) for model in self.models)


def _model_references(model: dict, file_name: str) -> bool:
    if file_name in model.get("css", ""):
        return True
    for template in model.get("tmpls", []):
        if file_name in template.get("qfmt", "") or file_name in template.get(
            "afmt", ""
        ):
            return True
    return False
