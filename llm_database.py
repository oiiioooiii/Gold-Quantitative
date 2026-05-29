"""
LLM对话历史数据库管理
使用SQLite持久化LLM分析对话
"""

import sqlite3
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from utils.logger import get_logger


class LLMDatabase:
    """LLM对话历史数据库"""
    
    def __init__(self, db_path: str = "llm_history.db"):
        self.db_path = db_path
        self.logger = get_logger()
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 对话会话表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            # 消息记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            ''')
            
            # 持仓分析记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS position_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    ticket INTEGER,
                    symbol TEXT,
                    position_type TEXT,
                    volume REAL,
                    open_price REAL,
                    current_price REAL,
                    profit REAL,
                    decision TEXT,
                    stop_loss_price REAL,
                    reason TEXT,
                    executed BOOLEAN DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            ''')
            
            conn.commit()
            conn.close()
            self.logger.info("LLM数据库初始化完成")
    
    def get_active_conversation(self, symbol: str) -> Optional[int]:
        """获取活跃的对话ID"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id FROM conversations WHERE symbol = ? AND status = ? ORDER BY start_time DESC LIMIT 1',
                (symbol, 'active')
            )
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
    
    def create_conversation(self, symbol: str) -> int:
        """创建新对话"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO conversations (symbol, status) VALUES (?, ?)',
                (symbol, 'active')
            )
            conversation_id = cursor.lastrowid
            conn.commit()
            conn.close()
            self.logger.info(f"创建新对话: ID={conversation_id}, 品种={symbol}")
            return conversation_id
    
    def add_message(self, conversation_id: int, role: str, content: str):
        """添加消息到对话"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
                (conversation_id, role, content)
            )
            conn.commit()
            conn.close()
    
    def get_conversation_history(self, conversation_id: int, limit: int = 20) -> List[Dict]:
        """获取对话历史"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT role, content, timestamp FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC LIMIT ?',
                (conversation_id, limit)
            )
            messages = [
                {
                    'role': row[0],
                    'content': row[1],
                    'timestamp': row[2]
                }
                for row in cursor.fetchall()
            ]
            conn.close()
            return messages
    
    def save_position_analysis(self, conversation_id: int, position_info: Dict, analysis_result: Dict, executed: bool = False):
        """保存持仓分析结果"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO position_analysis 
                (conversation_id, ticket, symbol, position_type, volume, open_price, current_price, profit, decision, stop_loss_price, reason, executed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                conversation_id,
                position_info.get('ticket'),
                position_info.get('symbol'),
                position_info.get('type'),
                position_info.get('volume'),
                position_info.get('open_price'),
                position_info.get('current_price'),
                position_info.get('profit'),
                'close' if analysis_result.get('should_close') else 'hold',
                analysis_result.get('stop_loss_price'),
                analysis_result.get('reason', ''),
                executed
            ))
            analysis_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return analysis_id
    
    def get_recent_analysis(self, symbol: str, limit: int = 10) -> List[Dict]:
        """获取最近的分析记录"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pa.*, c.start_time 
                FROM position_analysis pa
                JOIN conversations c ON pa.conversation_id = c.id
                WHERE pa.symbol = ?
                ORDER BY pa.timestamp DESC
                LIMIT ?
            ''', (symbol, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row[0],
                    'ticket': row[2],
                    'position_type': row[3],
                    'volume': row[4],
                    'open_price': row[5],
                    'current_price': row[6],
                    'profit': row[7],
                    'decision': row[8],
                    'stop_loss_price': row[9],
                    'reason': row[10],
                    'executed': bool(row[11]),
                    'timestamp': row[12]
                })
            conn.close()
            return results
    
    def build_context_prompt(self, conversation_id: int) -> str:
        """构建包含历史对话的提示词"""
        history = self.get_conversation_history(conversation_id, limit=10)
        if not history:
            return ""
        
        context_parts = ["[历史对话]"]
        for msg in history:
            role_label = "分析师" if msg['role'] == "assistant" else "用户"
            context_parts.append(f"{role_label}: {msg['content']}")
        
        context_parts.append("\n[当前分析]")
        return "\n".join(context_parts)
    
    def get_all_conversations(self, symbol: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        获取所有对话记录
        
        Args:
            symbol: 可选的品种过滤
            limit: 返回记录数限制
            
        Returns:
            对话记录列表
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute('''
                    SELECT id, symbol, start_time, end_time, status
                    FROM conversations
                    WHERE symbol = ?
                    ORDER BY start_time DESC
                    LIMIT ?
                ''', (symbol, limit))
            else:
                cursor.execute('''
                    SELECT id, symbol, start_time, end_time, status
                    FROM conversations
                    ORDER BY start_time DESC
                    LIMIT ?
                ''', (limit,))
            
            conversations = []
            for row in cursor.fetchall():
                conversations.append({
                    "id": row[0],
                    "symbol": row[1],
                    "start_time": row[2],
                    "end_time": row[3],
                    "status": row[4]
                })
            
            conn.close()
            return conversations
    
    def get_all_position_analysis(self, symbol: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        获取所有持仓分析记录
        
        Args:
            symbol: 可选的品种过滤
            limit: 返回记录数限制
            
        Returns:
            持仓分析记录列表
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute('''
                    SELECT pa.id, pa.conversation_id, pa.ticket, pa.symbol, 
                           pa.position_type, pa.volume, pa.open_price, 
                           pa.current_price, pa.profit, pa.decision, 
                           pa.stop_loss_price, pa.reason, pa.executed, 
                           pa.timestamp
                    FROM position_analysis pa
                    WHERE pa.symbol = ?
                    ORDER BY pa.timestamp DESC
                    LIMIT ?
                ''', (symbol, limit))
            else:
                cursor.execute('''
                    SELECT pa.id, pa.conversation_id, pa.ticket, pa.symbol, 
                           pa.position_type, pa.volume, pa.open_price, 
                           pa.current_price, pa.profit, pa.decision, 
                           pa.stop_loss_price, pa.reason, pa.executed, 
                           pa.timestamp
                    FROM position_analysis pa
                    ORDER BY pa.timestamp DESC
                    LIMIT ?
                ''', (limit,))
            
            analysis_list = []
            for row in cursor.fetchall():
                analysis_list.append({
                    "id": row[0],
                    "conversation_id": row[1],
                    "ticket": row[2],
                    "symbol": row[3],
                    "position_type": row[4],
                    "volume": row[5],
                    "open_price": row[6],
                    "current_price": row[7],
                    "profit": row[8],
                    "decision": row[9],
                    "stop_loss_price": row[10],
                    "reason": row[11],
                    "executed": bool(row[12]),
                    "timestamp": row[13]
                })
            
            conn.close()
            return analysis_list


# 全局数据库实例
_llm_db: Optional[LLMDatabase] = None


def get_llm_database() -> LLMDatabase:
    """获取LLM数据库单例"""
    global _llm_db
    if _llm_db is None:
        _llm_db = LLMDatabase()
    return _llm_db
