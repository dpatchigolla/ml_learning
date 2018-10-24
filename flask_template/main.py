from flask import render_template, Flask, request, jsonify

app = Flask(__name__)


@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')

@app.route('/result/<query>', methods=['GET'])
def test(query):
    debug = request.args.get('debug',False)
    method = request.args.get('method','ql')
    assert query!='test'
    resp = {'query':query}
    if debug:
        resp['debug'] = {'method':method}
    return jsonify(resp)



if __name__ == '__main__':
    app.run(debug=True)