from enum import StrEnum


class State(StrEnum):
    IDLE = "idle"
    REG_NAME = "reg_name"
    REG_GENDER = "reg_gender"
    REG_AGE = "reg_age"
    REG_FACULTY = "reg_faculty"
    REG_DORMITORY = "reg_dormitory"
    REG_PHOTOS = "reg_photos"
    REG_DESCRIPTION = "reg_description"

    REPORT_REASON = "report_reason"
    SUPPORT_MESSAGE = "support_message"
    SUPPORT_REPLY = "support_reply"

    ADMIN_SEARCH = "admin_search"
