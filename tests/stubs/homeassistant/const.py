from enum import StrEnum
class Platform(StrEnum):
    MEDIA_PLAYER='media_player'; SELECT='select'; BUTTON='button'; SWITCH='switch'; NUMBER='number'
class EntityCategory(StrEnum):
    CONFIG='config'; DIAGNOSTIC='diagnostic'
