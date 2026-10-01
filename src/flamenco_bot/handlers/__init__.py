from aiogram import Router

from .admin import router as admin_router
from .core import router as core_router
from .fallback import router as fallback_router
from ..keyboards.user.account import router as account_router
from ..keyboards.user.lessons import router as lessons_router
from ..keyboards.user.main_menu import router as main_menu_router

router = Router(name="bot")
router.include_router(core_router)
router.include_router(main_menu_router)
router.include_router(admin_router)
router.include_router(account_router)
router.include_router(lessons_router)
router.include_router(fallback_router)

__all__ = ["router"]
