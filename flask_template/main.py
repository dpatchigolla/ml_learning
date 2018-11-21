from flask import render_template, Flask, request, jsonify

app = Flask(__name__)


@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')

@app.route('/result/<query>', methods=['GET'])
def test(query):
    debug = request.args.get('debug',False)
    method = request.args.get('method','ql')
    int_val = request.args.get('int_val', 1, type=int) # adding type to parse args to appropriate datatype
    float_val = request.args.get('float_val', 0.1, type=float)
    assert query!='test'
    resp = {'query':query, 'int_val':int_val, 'float_val':float_val}
    if debug:
        resp['debug'] = {'method':method}
    return jsonify(resp)



if __name__ == '__main__':
    app.run(debug=True, port=5015)