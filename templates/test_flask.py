
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route('/input', methods=['GET'])
def sample_code():
    query = request.args.get('query','none')
    debug = request.args.get('debug',False)
    method = request.args.get('method','ql')
    assert query != 'test' # to test the debug mode. If 'test' is passed as param, it shows traceback
    if debug:
        return jsonify({'query':query, 'debug':{'method':method}})
    else:
        return jsonify({'query':query})




if __name__ == '__main__':
    app.run(debug=True)