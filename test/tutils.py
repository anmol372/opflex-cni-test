from time import sleep

def assertEventually(checker, delay, count):
    ix = 0
    err = ""
    while (ix < count):
        err = checker()
        if err == "":
            return
        ix += 1
        sleep(delay)
    print("Error is: {}".format(err))
    assert err == ""
