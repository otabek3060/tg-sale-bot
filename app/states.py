from aiogram.fsm.state import State, StatesGroup


class BuyStates(StatesGroup):
    waiting_receipt = State()


class AdminStates(StatesGroup):
    reject_reason = State()
    setting_value = State()
    setting_confirm = State()
    add_admin = State()
    search_user = State()
    message_user = State()
    broadcast_content = State()
    broadcast_confirm = State()
