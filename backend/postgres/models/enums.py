from enum import Enum

class GlobalRole(str, Enum):
    super_admin = "super_admin"
    admin = "admin",
    user = "user"

class CaseMembershipRole(str, Enum):
    owner = "owner"
    collaborator = "collaborator"