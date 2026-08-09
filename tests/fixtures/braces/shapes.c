/* Shapes the brace scanner has to get right. Nothing here is idiomatic; each
   function exists to pin one decision down. */
#include <stdio.h>
#include <stdlib.h>
#define WRAP(x) ((x) + 1)

/* A control keyword followed by a paren is not a function header. */
static int guarded(int a) {
    if (a > 0) {
        while (a--) {
            for (int i = 0; i < 3; i++) {
                switch (i) {
                case 0:
                    puts("deep");   /* four levels inside the body */
                    break;
                }
            }
        }
    }
    return a;
}

/* Six parameters, so the parameter rule has something to find. A default-ish
   argument with a comma inside parens must still count as one. */
int many(int a, int b, char *c, void (*cb)(int, int), double e, long f) {
    return a + b + (int) e + (int) f;
}

/* An apostrophe in a comment: don't let it open a string literal. */
char quoting(void) {
    char c = '\'';
    const char *s = "a \"quoted\" string with a } brace and a { brace";
    printf("%s %c\n", s, c);
    return c;
}

/* An initializer is not a function. */
static const int table[] = {1, 2, 3};

struct point { int x; int y; };

int shallow(void) { return table[0]; }
