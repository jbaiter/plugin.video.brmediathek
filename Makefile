package:
	mkdir -p ./plugin.video.brmediathek
	cp -R addon.* *.png *.jpg LICENSE resources ./plugin.video.brmediathek/
	zip -x \*.pyc  -r plugin.video.brmediathek.zip plugin.video.brmediathek
	rm -rf ./plugin.video.brmediathek
