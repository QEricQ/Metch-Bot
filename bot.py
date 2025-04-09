# 修改 imports
import os
import configparser
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
import aiohttp
import random
from datetime import datetime, timedelta
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# 配置日志和监控
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 初始化Prometheus指标
from prometheus_client import Counter, Histogram, start_http_server

# 定义监控指标
MESSAGE_COUNTER = Counter('bot_messages_total', 'Total number of messages processed', ['type'])
MATCH_COUNTER = Counter('bot_matches_total', 'Total number of successful matches')
RESPONSE_TIME = Histogram('bot_response_time_seconds', 'Time spent processing messages')
ACTIVE_USERS = Counter('bot_active_users_total', 'Number of active users')
ERROR_COUNTER = Counter('bot_errors_total', 'Total number of errors', ['type'])

# 启动Prometheus指标服务器
start_http_server(8000)

# 读取配置文件
config = configparser.ConfigParser()
config.read('config.ini')

# 初始化 Firebase Admin SDK
cred = credentials.Certificate("service-account.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': config['firebase']['database_url'],
    'projectId': config['firebase']['project_id'],
    'storageBucket': config['firebase']['storage_bucket'],
    'authDomain': config['firebase']['auth_domain']
})
db_ref = db.reference('/')

# 修改数据存储相关代码
# 添加新的 import
from google.auth.exceptions import TransportError
import time

# 添加重试函数
def retry_operation(operation, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return operation()
        except TransportError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(1)  # 等待1秒后重试

# 修改 set_preference 函数
async def set_preference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("请使用正确的格式：/setpreference <兴趣类型> <具体偏好>\n例如：/setpreference '电影' '科幻片'")
        return
    
    interest_type = context.args[0]
    specific_interest = context.args[1]
    
    try:
        def db_operation():
            user_ref = db_ref.child('user_preferences').child(user_id)
            user_ref.set({
                'user_id': user_id,
                'interest_type': interest_type,
                'specific_interest': specific_interest,
                'timestamp': str(datetime.now())
            })
        
        retry_operation(db_operation)
        await update.message.reply_text(f"已保存你的兴趣爱好！\n类型：{interest_type}\n偏好：{specific_interest}")
    except Exception as e:
        logging.error(f"Firebase operation failed: {str(e)}")
        await update.message.reply_text("抱歉，保存失败。请稍后重试。")

# 修改查找匹配的代码
def calculate_interest_similarity(user_prefs, other_prefs):
    # 创建用户兴趣文本
    user_text = f"{user_prefs['interest_type']} {user_prefs['specific_interest']}"
    other_text = f"{other_prefs['interest_type']} {other_prefs['specific_interest']}"
    
    # 使用TF-IDF计算文本相似度
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform([user_text, other_text])
    similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
    return similarity

def calculate_activity_score(user_id):
    # 获取用户最近的活动记录
    messages = db_ref.child('messages').order_by_child('timestamp').limit_to_last(50).get()
    if not messages:
        return 0
    
    user_messages = [msg for msg in messages.values() if msg['user_id'] == user_id]
    recent_activity = len(user_messages)
    return min(recent_activity / 10, 1)  # 归一化分数

async def find_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # 获取当前用户偏好和位置信息
    user_prefs = db_ref.child('user_preferences').child(user_id).get()
    if not user_prefs:
        await update.message.reply_text("请先使用 /setpreference 命令设置你的兴趣爱好！")
        return
    
    # 获取所有用户偏好
    all_users = db_ref.child('user_preferences').get()
    if not all_users:
        await update.message.reply_text("🔍 *暂时没有找到兴趣相投的用户*\n建议稍后再试！", parse_mode='Markdown')
        return
    
    # 计算匹配分数
    matches = []
    for other_id, other_prefs in all_users.items():
        if other_id != user_id:  # 排除自己
            # 计算兴趣相似度
            interest_similarity = calculate_interest_similarity(user_prefs, other_prefs)
            
            # 计算活跃度分数
            activity_score = calculate_activity_score(other_id)
            
            # 综合评分
            match_score = 0.6 * interest_similarity + 0.4 * activity_score
            
            if match_score > 0.3:  # 设置匹配阈值
                matches.append({
                    'user_id': other_id,
                    'prefs': other_prefs,
                    'score': match_score
                })
    
    # 按匹配分数排序
    matches.sort(key=lambda x: x['score'], reverse=True)
    
    if not matches:
        await update.message.reply_text("🔍 *暂时没有找到兴趣相投的用户*\n建议稍后再试！", parse_mode='Markdown')
        return
    
    response = "*🎯 找到以下与你兴趣相投的朋友：*\n\n"
    for match in matches[:5]:  # 只显示前5个最佳匹配
        match_percentage = int(match['score'] * 100)
        response += f"👤 *{match['prefs']['interest_type']}*\n"
        response += f"└ 偏好：{match['prefs']['specific_interest']}\n"
        response += f"└ 匹配度：{match_percentage}%\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

# 修改聊天记录存储
def get_user_chat_history(user_id, limit=10):
    # 获取用户最近的聊天记录
    messages = db_ref.child('messages').order_by_child('timestamp').limit_to_last(limit).get()
    if not messages:
        return []
    return [msg for msg in messages.values() if msg['user_id'] == user_id]

def analyze_user_interests(chat_history):
    # 分析用户聊天记录中的关键词
    text = ' '.join([msg['message'] for msg in chat_history])
    vectorizer = TfidfVectorizer(max_features=10)
    try:
        tfidf_matrix = vectorizer.fit_transform([text])
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.toarray()[0]
        keywords = [(feature_names[i], scores[i]) for i in range(len(feature_names))]
        keywords.sort(key=lambda x: x[1], reverse=True)
        return keywords[:5]
    except:
        return []

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_message = update.message.text
    
    # 获取用户兴趣偏好和聊天历史
    user_prefs = db_ref.child('user_preferences').child(user_id).get()
    chat_history = get_user_chat_history(user_id)
    keywords = analyze_user_interests(chat_history)
    
    interest_context = ""
    if user_prefs:
        interest_type = user_prefs.get('interest_type')
        specific_interest = user_prefs.get('specific_interest')
        interest_context = f"我对{interest_type}特别感兴趣，尤其喜欢{specific_interest}。"
        if keywords:
            interest_context += f"\n根据我的聊天记录，我还经常讨论：{', '.join([k[0] for k in keywords])}。"
    
    # 构建完整的提问内容
    prompt = f"""
用户背景：{interest_context}
用户问题：{user_message}

请根据用户的兴趣爱好，提供相关的建议和推荐。回答要具体且实用。
如果是推荐内容，请包含：
1. 最新热门内容
2. 经典推荐
3. 相关活动或资讯
"""
    
    # 存储用户消息
    message_ref = db_ref.child('messages').push()
    message_ref.set({
        'user_id': user_id,
        'message': user_message,
        'timestamp': str(datetime.now()),
        'type': 'user'
    })
    
    # HKBU API 调用
    async with aiohttp.ClientSession() as session:
        async with session.post(
            config['CHATGPT']['BASICURL'],
            headers={'Authorization': f"Bearer {config['CHATGPT']['ACCESS_TOKEN']}"},
            json={
                'message': prompt,
                'model': config['CHATGPT']['MODELNAME'],
                'api-version': config['CHATGPT']['APIVERSION']
            }
        ) as response:
            if response.status == 200:
                bot_response = await response.json()
                await update.message.reply_text(bot_response['response'], parse_mode='Markdown')
                
                # 存储机器人回复
                message_ref = db_ref.child('messages').push()
                message_ref.set({
                    'user_id': 'bot',
                    'message': bot_response['response'],
                    'timestamp': str(datetime.now()),
                    'type': 'bot'
                })
            else:
                await update.message.reply_text("抱歉，我现在无法回答。请稍后再试。")

# 在 Firebase 初始化之后添加 start 函数
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理/start命令"""
    welcome_message = """
👋 *欢迎使用兴趣匹配机器人！*

我可以帮你：
📝 设置兴趣爱好
🔍 查找志同道合的朋友
🎯 获取个性化推荐
💬 聊天答疑

*常用命令：*
• /start - 显示此帮助信息
• /setpreference - 设置兴趣爱好
• /findmatches - 查找朋友
• /recommendations - 获取推荐内容

*使用示例：*
`/setpreference 单机游戏 "剧情向RPG"`
`/setpreference 电影 "科幻片"`
`/setpreference 小说 "奇幻文学"`
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

# 添加推荐函数
async def get_recommendations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # 获取用户偏好
    user_prefs = db_ref.child('user_preferences').child(user_id).get()
    if not user_prefs:
        await update.message.reply_text("请先使用 /setpreference 命令设置你的兴趣爱好！")
        return
    
    interest_type = user_prefs.get('interest_type')
    specific_interest = user_prefs.get('specific_interest')
    
    # 构建推荐请求
    prompt = f"""
作为推荐系统，请根据用户的兴趣提供个性化推荐：
兴趣类型：{interest_type}
具体偏好：{specific_interest}

请提供以下内容：
1. 3个最新热门内容推荐
2. 2个经典内容推荐
3. 2个相关活动或资讯

注意：
- 推荐要具体且实用
- 包含实际的内容名称和简短说明
- 使用emoji增加可读性
- 确保推荐与用户兴趣高度相关
"""

    # 调用 HKBU API 获取推荐
    try:
        async with aiohttp.ClientSession() as session:
            url = (config['CHATGPT']['BASICURL'] + "/deployments/" +
                   config['CHATGPT']['MODELNAME'] + "/chat/completions/?api-version=" +
                   config['CHATGPT']['APIVERSION'])
            
            headers = {
                'Content-Type': 'application/json',
                'api-key': config['CHATGPT']['ACCESS_TOKEN']
            }
            
            payload = {
                'messages': [{"role": "user", "content": prompt}]
            }
            
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    bot_response = await response.json()
                    # 构建响应消息
                    response = f"""
*📢 根据你的兴趣为你推荐：*
*类型：* {interest_type}
*偏好：* {specific_interest}

{bot_response['choices'][0]['message']['content']}
"""
                    await update.message.reply_text(response, parse_mode='Markdown')
                else:
                    logging.error(f"API request failed with status code: {response.status}")
                    response_text = await response.text()
                    logging.error(f"API response: {response_text}")
                    raise Exception(f"API request failed with status {response.status}")
    except Exception as e:
        logging.error(f"Error calling HKBU API: {str(e)}")
        await update.message.reply_text("抱歉，获取推荐失败，请稍后重试。")
        return

def main():
    """主函数"""
    # 创建应用实例
    application = Application.builder().token(config['telegram']['bot_token']).build()
    # 添加处理程序
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setpreference", set_preference))
    application.add_handler(CommandHandler("findmatches", find_matches))
    application.add_handler(CommandHandler("recommendations", get_recommendations))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    
    # 启动机器人
    application.run_polling()

if __name__ == '__main__':
    main()