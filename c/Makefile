# C99 reference implementation.  The weights and vectors are generated:
#   python scripts/18_export_c.py
CC      ?= gcc
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wno-unused-parameter
LDLIBS  ?= -lm

all: test_forward test_features test_policy test_checked

test_forward: test_forward.c jev_head.c jev_head.h jev_head_weights.h test_vectors.h test_common.h
	$(CC) $(CFLAGS) -o $@ test_forward.c jev_head.c $(LDLIBS)

test_features: test_features.c jev_head.c jev_head.h jev_head_weights.h test_features.h test_common.h
	$(CC) $(CFLAGS) -o $@ test_features.c jev_head.c $(LDLIBS)

test_policy: test_policy.c jev_head.c jev_head.h jev_head_weights.h test_policy.h test_common.h
	$(CC) $(CFLAGS) -o $@ test_policy.c jev_head.c $(LDLIBS)

test_checked: test_checked.c jev_head.c jev_head.h jev_head_weights.h
	$(CC) $(CFLAGS) -o $@ test_checked.c jev_head.c $(LDLIBS)

check: all
	./test_forward
	./test_features
	./test_policy
	./test_checked

clean:
	rm -f test_forward test_features test_policy test_checked *.exe *.o

.PHONY: all check clean
