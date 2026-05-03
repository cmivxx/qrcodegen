import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.pylibs'))

from flask import Flask, redirect
from qr_generator import qr_bp

app = Flask(__name__)
app.register_blueprint(qr_bp)

@app.route('/')
def index():
    return redirect('/generator')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(port=port, debug=True)
