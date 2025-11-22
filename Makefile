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


reset:
	@(rm -rf .git && \
	  git init && \
	  git branch -m main && \
	  git remote add origin git@github.com:frnsimoes/frnsimoes.github.io.git && \
	  git add . && \
	  git commit -m 'init' && \
	  git push --force --set-upstream origin main)


