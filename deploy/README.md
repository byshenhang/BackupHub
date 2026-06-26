# Backup-Hub 部署文档

## 环境要求

- Python 3.10+
- Git（用于 Git 备份执行器）
- 网络访问：GitLab API、OSS 端点（如使用）

## Linux 部署（systemd）

### 1. 准备

```bash
# 创建部署目录
sudo mkdir -p /opt/backup-hub
sudo chown $USER:$USER /opt/backup-hub

# 复制代码
cp -r . /opt/backup-hub/

# 创建虚拟环境
cd /opt/backup-hub
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制并编辑配置文件
cp .env.example .env
vim .env

# 至少需要配置：
# - SECRET_KEY（加密密钥）
# - GITLAB_URL
# - GITLAB_TOKEN
```

### 3. 初始化数据库

```bash
python -m scripts.init_db
```

### 4. 安装系统服务

```bash
# 复制服务文件
sudo cp deploy/backup-hub.service /etc/systemd/system/

# 创建服务用户（可选）
sudo useradd -r -s /sbin/nologin backup-hub
sudo chown -R backup-hub:backup-hub /opt/backup-hub

# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable --now backup-hub

# 查看状态
sudo systemctl status backup-hub

# 查看日志
sudo journalctl -u backup-hub -f
```

### 5. 访问

浏览器打开 http://your-server:8000

## Windows 部署（NSSM）

### 1. 准备

```powershell
# 创建部署目录
mkdir C:\backup-hub
# 复制代码到 C:\backup-hub

# 创建虚拟环境
cd C:\backup-hub
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

```powershell
# 复制并编辑配置文件
copy .env.example .env
notepad .env
```

### 3. 初始化数据库

```powershell
python -m scripts.init_db
```

### 4. 安装系统服务

下载 [NSSM](https://nssm.cc/download) 并将 `nssm.exe` 放到 PATH 中，然后运行：

```powershell
deploy\install-service.bat
```

或手动安装：

```powershell
nssm install BackupHub "C:\backup-hub\venv\Scripts\python.exe" "-m" "app.main"
nssm set BackupHub AppDirectory "C:\backup-hub"
nssm set BackupHub Start SERVICE_AUTO_START
nssm start BackupHub
```

## 生成加密密钥

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将生成的密钥填入 `.env` 文件的 `SECRET_KEY` 字段。
