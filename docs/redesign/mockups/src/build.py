import sys, pathlib
src = pathlib.Path(__file__).parent
out = pathlib.Path('/var/home/oak/Codes/projects/tablet-wall-ai/docs/redesign/mockups'); out.mkdir(parents=True, exist_ok=True)
for n in sys.argv[1:]:
    # final.html has its own head (tokens.css inlined) and stage script; a/b/c keep the original shared files
    final = (src / f'{n}.head.html').exists()
    head = (src / f'{n}.head.html' if final else src / 'head.html').read_text()
    if final:
        head = head.replace('/*@TOKENS@*/', (src / 'tokens.css').read_text())
    stage = (src / ('stage-final.js' if final else 'stage.js')).read_text()
    body = (src / f'{n}.body.html').read_text().replace('/*@STAGE@*/', stage)
    (out / f'{n}.html').write_text('<!doctype html>\n<html lang="en">\n<head>\n' + head + body)
    print('built', n)
