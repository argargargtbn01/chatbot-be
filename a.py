from flask import Flask, request, jsonify
from transformers import AutoTokenizer, AutoModelForCausalLM
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Cấu hình cơ sở dữ liệu PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:argargargtbn1@localhost:5432/chatbot'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Khởi tạo mô hình và tokenizer
model_name = "EleutherAI/gpt-neo-125M"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# Models cho SQLAlchemy
class Chat(db.Model):
    __tablename__ = 'chat'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender = db.Column(db.String, nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Tạo bảng nếu chưa có
with app.app_context():
    db.create_all()

def generate_response(user_input):
    """
    Sinh phản hồi từ mô hình dựa trên đầu vào từ người dùng.
    """
    prompt = f"Solve this math problem: {user_input}"
    inputs = tokenizer(prompt, return_tensors="pt")
    outputs = model.generate(inputs['input_ids'], max_length=50, num_return_sequences=1)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def get_or_create_chat(session_name):
    """
    Lấy phiên hội thoại nếu đã tồn tại hoặc tạo phiên mới nếu chưa có.
    """
    new_chat = Chat(name=session_name)
    db.session.add(new_chat)
    db.session.commit()
    return new_chat

@app.route('/chat', methods=['POST'])
def chat():
    """
    API để xử lý cuộc hội thoại của người dùng. Nếu không có chat_id,
    sẽ tạo một phiên hội thoại mới.
    """
    data = request.get_json()
    chat_id = data.get('chat_id')
    user_message = data.get('message')

    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    # Xử lý tạo hoặc lấy chat_id
    if not chat_id:
        session_name = user_message[:30]
        chat_session = get_or_create_chat(session_name)
        chat_id = chat_session.id
    else:
        chat_session = Chat.query.filter_by(id=chat_id).first()
        if not chat_session:
            return jsonify({'error': 'Invalid chat_id'}), 400

    # Lưu tin nhắn của người dùng
    user_msg = Message(chat_id=chat_id, sender="User", content=user_message)
    db.session.add(user_msg)

    # Gọi hàm generate_response để tạo phản hồi từ bot
    bot_response = generate_response(user_message)

    # Lưu phản hồi của bot
    bot_msg = Message(chat_id=chat_id, sender="Bot", content=bot_response)
    db.session.add(bot_msg)
    db.session.commit()

    return jsonify({'chat_id': chat_id, 'response': bot_response})

@app.route('/chat-session', methods=['GET'])
def get_chat_sessions():
    """
    API để lấy danh sách các phiên hội thoại, sắp xếp theo thứ tự giảm dần của created_at.
    """
    chat_sessions = Chat.query.order_by(Chat.created_at.desc()).all()
    result = [{"chat_id": chat.id, "name": chat.name} for chat in chat_sessions]
    return jsonify(result)

@app.route('/message', methods=['GET'])
def get_messages():
    """
    API để lấy tất cả các tin nhắn trong một phiên hội thoại,
    sắp xếp theo thứ tự giảm dần của created_at.
    """
    chat_id = request.args.get('chat_id')
    if not chat_id:
        return jsonify({'error': 'No chat_id provided'}), 400

    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.created_at.desc()).all()
    result = [{"sender": msg.sender, "content": msg.content, "created_at": msg.created_at.isoformat()} for msg in messages]
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
