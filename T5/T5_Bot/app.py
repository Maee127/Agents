# pip install transformers flask flask-cors

from transformers import T5Tokenizer, T5ForConditionalGeneration
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')
CORS(app)

# Load the T5 model and tokenizer
model_name = 't5-base'
logger.info(f"Loading model: {model_name}")
tokenizer = T5Tokenizer.from_pretrained(model_name)
model = T5ForConditionalGeneration.from_pretrained(model_name)
logger.info("Model loaded successfully")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/summarize', methods=['POST'])
def summarize():
    try:
        input_text = request.form.get('inputText', '').strip()
        if not input_text:
            return "Error: No input text provided", 400
            
        summary_input = f'summarize: {input_text}'
        summary_input_ids = tokenizer.encode(summary_input, return_tensors='pt', truncation=True, max_length=512)
        summary_outputs = model.generate(
            summary_input_ids, 
            max_length=150,  # Increased for better summaries
            min_length=30,
            num_beams=4, 
            early_stopping=True,
            no_repeat_ngram_size=2
        )
        summary_text = tokenizer.decode(summary_outputs[0], skip_special_tokens=True)
        return summary_text
    except Exception as e:
        logger.error(f"Error in summarize: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/translate', methods=['POST'])
def translate():
    try:
        input_text = request.form.get('inputText', '').strip()
        source_language = request.form.get('sourceLanguage', 'English')
        target_language = request.form.get('targetLanguage', 'French')
        
        if not input_text:
            return "Error: No input text provided", 400
            
        # Validate language codes for T5
        language_map = {
            'English': 'English',
            'French': 'French',
            'German': 'German'
        }
        
        source = language_map.get(source_language, 'English')
        target = language_map.get(target_language, 'French')
        
        translation_input = f'translate {source} to {target}: {input_text}'
        logger.info(f"Translation input: {translation_input}")
        
        translation_input_ids = tokenizer.encode(translation_input, return_tensors='pt', truncation=True, max_length=512)
        translation_outputs = model.generate(
            translation_input_ids, 
            max_length=200,
            min_length=30,
            num_beams=4, 
            early_stopping=True
        )
        translated_text = tokenizer.decode(translation_outputs[0], skip_special_tokens=True)
        return translated_text
    except Exception as e:
        logger.error(f"Error in translate: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/translate-summary', methods=['POST'])
def translate_summary():
    try:
        summary_text = request.form.get('summaryText', '').strip()
        source_language = request.form.get('sourceLanguage', 'English')
        target_language = request.form.get('targetLanguage', 'French')
        
        if not summary_text:
            return "Error: No summary text provided", 400
            
        translation_summary_input = f'translate {source_language} to {target_language}: {summary_text}'
        translation_summary_input_ids = tokenizer.encode(translation_summary_input, return_tensors='pt', truncation=True, max_length=512)
        translated_summary_outputs = model.generate(
            translation_summary_input_ids, 
            max_length=150,
            min_length=20,
            num_beams=4, 
            early_stopping=True
        )
        translated_summary_text = tokenizer.decode(translated_summary_outputs[0], skip_special_tokens=True)
        return translated_summary_text
    except Exception as e:
        logger.error(f"Error in translate_summary: {str(e)}")
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0')