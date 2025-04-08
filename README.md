# Telegram 聊天机器人项目

这是一个基于Telegram的智能聊天机器人，集成了HKBU的ChatGPT API，使用Google Cloud Platform和Firebase进行部署和数据存储。

## 功能特点

- 智能对话：使用HKBU的ChatGPT API进行自然语言交互
- 数据存储：使用Firebase实时数据库存储聊天记录
- 容器化部署：使用Docker和Docker Compose进行服务编排
- 监控系统：集成Prometheus和Grafana进行性能监控

## 安装步骤

1. 克隆项目代码
2. 配置环境变量
   - 复制`config.ini.example`为`config.ini`
   - 填入必要的配置信息：
     - Telegram Bot Token
     - HKBU API密钥
     - Firebase配置
     - Google Cloud配置

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 运行项目
```bash
# 直接运行
python bot.py

# 使用Docker运行
docker-compose up -d
```

## 配置说明

### Telegram Bot配置
1. 访问 @BotFather 创建新的机器人
2. 获取Bot Token并填入config.ini

### Firebase配置
1. 在Firebase Console创建新项目
2. 获取项目配置信息
3. 下载服务账号密钥文件

### Google Cloud配置
1. 创建新的GCP项目
2. 启用必要的API
3. 配置服务账号和权限

## 监控系统

项目集成了Prometheus和Grafana用于监控：
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

## 技术栈

- Python 3.9
- python-telegram-bot
- Google Cloud Platform
- Firebase
- Docker & Docker Compose
- Prometheus & Grafana

## 注意事项

- 确保所有敏感信息都在config.ini中配置
- 定期检查日志和监控面板
- 遵循最佳安全实践