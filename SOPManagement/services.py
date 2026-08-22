"""
SOP Management Services — business logic / writes.

Views call these functions for anything that mutates data. Selectors stay
read-only; validators stay pure. This mirrors the layered pattern used in
Brass_QC/services/{selectors,validators,submission_service}.py.
"""
import logging

from django.db import transaction

from .models import SOPMaster
from .selectors import get_other_active_sops_for_module

logger = logging.getLogger(__name__)


def create_sop(*, module_id, sop_title, version, description, file_obj, is_active, user):
    """
    Create a new SOPMaster row. If is_active is True, archives every other
    active SOP for the same module inside the same transaction so exactly
    one active SOP per module is ever visible to users.
    """
    logger.info(
        '[SOP_CREATE] [INPUT] module_id=%s sop_title=%s version=%s is_active=%s user=%s',
        module_id, sop_title, version, is_active, user,
    )
    with transaction.atomic():
        if is_active:
            archived_count = (
                get_other_active_sops_for_module(module_id)
                .select_for_update()
                .update(is_active=False, updated_by=user)
            )
            if archived_count:
                logger.info(
                    '[SOP_CREATE] archived %d previous active SOP(s) for module_id=%s',
                    archived_count, module_id,
                )

        sop = SOPMaster.objects.create(
            module_id=module_id,
            sop_title=sop_title,
            version=version,
            description=description or '',
            file=file_obj,
            file_name=file_obj.name,
            file_size=file_obj.size,
            uploaded_by=user,
            updated_by=user,
            is_active=is_active,
        )

    logger.info('[SOP_CREATE] [SUCCESS] sop_id=%s module_id=%s', sop.id, module_id)
    return sop


def update_sop(*, sop_id, user, sop_title=None, version=None, description=None,
                file_obj=None, is_active=None):
    """
    Update an existing SOP. Replacing the file, changing version/description,
    and flipping active status are all supported. Activating this SOP
    archives every other active SOP for the same module.
    """
    logger.info('[SOP_UPDATE] [INPUT] sop_id=%s user=%s', sop_id, user)
    with transaction.atomic():
        sop = SOPMaster.objects.select_for_update().filter(pk=sop_id, is_deleted=False).first()
        if sop is None:
            return None

        if sop_title is not None:
            sop.sop_title = sop_title
        if version is not None:
            sop.version = version
        if description is not None:
            sop.description = description
        if file_obj is not None:
            sop.file = file_obj
            sop.file_name = file_obj.name
            sop.file_size = file_obj.size

        activating = is_active is True and not sop.is_active
        if is_active is not None:
            sop.is_active = is_active

        if activating or (is_active and sop.is_active):
            archived_count = (
                get_other_active_sops_for_module(sop.module_id, exclude_id=sop.id)
                .select_for_update()
                .update(is_active=False, updated_by=user)
            )
            if archived_count:
                logger.info(
                    '[SOP_UPDATE] archived %d previous active SOP(s) for module_id=%s',
                    archived_count, sop.module_id,
                )

        sop.updated_by = user
        sop.save()

    logger.info('[SOP_UPDATE] [SUCCESS] sop_id=%s', sop.id)
    return sop


def soft_delete_sop(*, sop_id, user):
    """Soft delete only — sets is_deleted=True and is_active=False."""
    logger.info('[SOP_DELETE] [INPUT] sop_id=%s user=%s', sop_id, user)
    with transaction.atomic():
        sop = SOPMaster.objects.select_for_update().filter(pk=sop_id, is_deleted=False).first()
        if sop is None:
            return None
        sop.is_deleted = True
        sop.is_active = False
        sop.updated_by = user
        sop.save(update_fields=['is_deleted', 'is_active', 'updated_by', 'updated_at'])

    logger.info('[SOP_DELETE] [SUCCESS] sop_id=%s', sop_id)
    return sop
