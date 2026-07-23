from mutohplot.hpgl.tokenizer import HPGLTokenizer

def test_tokenizer_basic_commands():
    commands = HPGLTokenizer().tokenize("IN;SP1;PA10,20;")
    assert [c.name for c in commands] == ["IN", "SP", "PA"]
    assert commands[1].numeric_args == [1.0]
    assert commands[2].numeric_args == [10.0, 20.0]
