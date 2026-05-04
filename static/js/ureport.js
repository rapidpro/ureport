// Utility method to convert integers to strings with commas in them.
// Sadly this isn't locale aware yet.
var intcomma = function (value) {
  var origValue = String(value);
  var newValue = origValue.replace(/^(-?\d+)(\d{3})/, '$1,$2');
  if (origValue === newValue) {
    return newValue;
  } else {
    return intcomma(newValue);
  }
};

window.intcomma = intcomma;

// debouncedresize: special jQuery event that happens once after a window resize
//
// latest version and complete README available on Github:
// https://github.com/louisremi/jquery-smartresize
//
// Copyright 2012 @louis_remi
// Licensed under the MIT license.
(function ($) {
  var $event = $.event;
  var resizeTimeout;
  var $special = $event.special.debouncedresize = {
    setup: function () {
      $(this).on("resize", $special.handler);
    },

    teardown: function () {
      $(this).off("resize", $special.handler);
    },

    handler: function (event, execAsap) {
      // Save the context
      var context = this;
      var args = arguments;
      var dispatch = function () {
        // set correct event type
        event.type = "debouncedresize";
        $event.dispatch.apply(context, args);
      };

      if (resizeTimeout) {
        clearTimeout(resizeTimeout);
      }
      if (execAsap) {
        dispatch();
      } else {
        resizeTimeout = setTimeout(dispatch, $special.threshold);
      }
    },

    threshold: 150
  };
})(jQuery);
