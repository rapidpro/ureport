#
# * debouncedresize: special jQuery event that happens once after a window resize
# *
# * latest version and complete README available on Github:
# * https://github.com/louisremi/jquery-smartresize
# *
# * Copyright 2012 @louis_remi
# * Licensed under the MIT license.
# *
# * This saved you an hour of work?
# * Send me music http://www.amazon.co.uk/wishlist/HNTU0468LQON
#
(($) ->
  $event = $.event
  $special = undefined
  resizeTimeout = undefined
  $special = $event.special.debouncedresize =
    setup: ->
      $(this).on "resize", $special.handler
      return

    teardown: ->
      $(this).off "resize", $special.handler
      return

    handler: (event, execAsap) ->

      # Save the context
      context = this
      args = arguments
      dispatch = ->

        # set correct event type
        event.type = "debouncedresize"
        $event.dispatch.apply context, args
        return

      clearTimeout resizeTimeout  if resizeTimeout
      (if execAsap then dispatch() else resizeTimeout = setTimeout(dispatch, $special.threshold))
      return

    threshold: 150

  return
) jQuery