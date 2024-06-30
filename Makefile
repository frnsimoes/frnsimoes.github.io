.PHONY: clean build p

clean:
	rm -rf public/

build: clean
	hugo

p: build
	git add .
	@read -p "commit:" commit; \
	git commit -m "$$commit"; \
	git push origin main
