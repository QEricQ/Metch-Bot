import pytest
from unittest.mock import Mock, patch, AsyncMock
from telegram import Update
from telegram.ext import ContextTypes
import bot

@pytest.fixture
def mock_update():
    update = Mock(spec=Update)
    update.effective_user = Mock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = ['电影', '科幻片']
    return context

@pytest.fixture
def mock_db_ref():
    return Mock()

@pytest.mark.asyncio
async def test_set_preference(mock_update, mock_context, mock_db_ref):
    with patch('bot.db_ref', mock_db_ref):
        # 模拟数据库操作
        mock_child = Mock()
        mock_db_ref.child.return_value.child.return_value = mock_child
        
        # 执行测试
        await bot.set_preference(mock_update, mock_context)
        
        # 验证结果
        mock_update.message.reply_text.assert_called_once()
        assert '已保存你的兴趣爱好' in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_find_matches(mock_update, mock_context, mock_db_ref):
    with patch('bot.db_ref', mock_db_ref):
        # 模拟用户偏好数据
        user_prefs = {
            'interest_type': '电影',
            'specific_interest': '科幻片'
        }
        all_users = {
            '123456': user_prefs,
            '789012': {
                'interest_type': '电影',
                'specific_interest': '动作片'
            }
        }
        
        # 设置模拟数据库调用的返回值
        preferences_ref = Mock()
        preferences_ref.get.return_value = all_users
        
        user_ref = Mock()
        user_ref.get.return_value = user_prefs
        
        mock_db_ref.child.return_value = preferences_ref
        preferences_ref.child.return_value = user_ref
        
        # 执行测试
        await bot.find_matches(mock_update, mock_context)
        
        # 验证结果
        mock_update.message.reply_text.assert_called_once()