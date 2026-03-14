import os
import json
import shutil
import cv2
import numpy as np
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import base64
from pydantic import BaseModel

class ImageData(BaseModel):
    filename: str
    base64: str

app = FastAPI(title="Asset Master Pipeline API")

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化目录
RAW_DIR = "assets/raw"
PROC_DIR = "assets/processed"
DB_FILE = "database.json"

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PROC_DIR, exist_ok=True)

# --- 数据库模拟 (持久化保存进度) ---
def load_db():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- 静态文件托管 ---
# 这样你可以直接通过 http://localhost:8000/ 访问你的 HTML
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

# --- API 1: 获取所有素材进度 ---
@app.get("/api/assets")
def get_assets():
    return load_db()

# --- API 2: 上传素材入库 ---
@app.post("/api/upload")
async def upload_asset(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1]
    asset_id = f"AST_{uuid.uuid4().hex[:8].upper()}"
    save_filename = f"{asset_id}.{ext}"
    file_path = os.path.join(RAW_DIR, save_filename)
    
    # 将文件保存到本地硬盘
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 写入数据库
    db = load_db()
    new_asset = {
        "id": asset_id,
        "name": file.filename,
        "url": f"/assets/raw/{save_filename}",
        "status": "UNPROCESSED"
    }
    db.append(new_asset)
    save_db(db)
    
    return new_asset

# --- API 3: OpenCV 工业流水线处理演示 ---
@app.post("/api/process/{asset_id}")
def process_asset(asset_id: str):
    db = load_db()
    asset = next((a for a in db if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    # 获取本地原图路径
    filename = asset["url"].split("/")[-1]
    raw_path = os.path.join(RAW_DIR, filename)
    proc_path = os.path.join(PROC_DIR, f"proc_{filename}")
    
    # 🌟 OpenCV 图像处理魔法开始 🌟
    # 读取图像（包含透明通道）
    img = cv2.imread(raw_path, cv2.IMREAD_UNCHANGED)
    
    if img is not None:
        # 演示功能：提取边缘并高亮 (类似你的物理描边)
        # 实际开发中，这里可以换成更复杂的 Python 算法
        if img.shape[2] == 4: # 如果有 Alpha 通道
            b, g, r, a = cv2.split(img)
            # 简单的 OpenCV 处理：将主体转换为灰度复古风，保留透明度
            gray = cv2.cvtColor(cv2.merge([b,g,r]), cv2.COLOR_BGR2GRAY)
            processed_img = cv2.merge([gray, gray, gray, a])
        else:
            processed_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
        # 保存处理后的图像
        cv2.imwrite(proc_path, processed_img)
        
        # 更新数据库状态
        asset["url"] = f"/assets/processed/proc_{filename}"
        asset["status"] = "PROCESSED"
        save_db(db)
        
        return {"message": "OpenCV 处理完成", "asset": asset}
    else:
        raise HTTPException(status_code=500, detail="OpenCV 无法读取该图像")
    
    # --- API 4: 工作流暂存接口 (流水线回传) ---
@app.post("/api/pipeline_save")
def pipeline_save(data: ImageData):
    # 解析 base64
    header, encoded = data.base64.split(",", 1)
    file_data = base64.b64decode(encoded)
    
    ext = data.filename.split(".")[-1] if "." in data.filename else "png"
    asset_id = f"AST_{uuid.uuid4().hex[:8].upper()}"
    save_filename = f"{asset_id}.{ext}"
    
    # 存入处理后的文件夹
    file_path = os.path.join(PROC_DIR, save_filename)
    with open(file_path, "wb") as f:
        f.write(file_data)
        
    db = load_db()
    new_asset = {
        "id": asset_id,
        "name": data.filename,
        "url": f"/assets/processed/{save_filename}",
        "status": "INTERMEDIATE"  # 🌟 新增状态：中间暂存区
    }
    db.append(new_asset)
    save_db(db)
    
    return new_asset