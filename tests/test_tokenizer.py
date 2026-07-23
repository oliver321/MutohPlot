from mutohplot.hpgl.tokenizer import Tokenizer

def test_tokenizer():
    cmds=Tokenizer().tokenize("IN;SP1;PA10,20;")
    assert cmds[0].name=="IN"
    assert cmds[1].args==["1"]
