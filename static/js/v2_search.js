// wire in our search boxes
$(function () {
  $(".search-box").focusin(function () {
    var searchBox = $(this);
    var results = "#" + $(this).data("results-id");
    if (!$(results).hasClass("shown")) {
      $(results).addClass("shown");
      $(document).on("click.searchBox", function () {
        $(searchBox).val("");
        $(results).find(".no-results").addClass("hidden");
        $(results).find(".searchable").removeClass("hide");
        $(results).find(".search-category").removeClass("hidden").removeClass("open");
        $(results).removeClass("shown");
        $(document).off("click.searchBox");
      });
    }
  });

  $(".search-close").click(function () {
    var results = "#" + $(this).data("results-id");
    $(results).toggleClass("shown");
  });

  // don't bubble events past our search results or box
  $(".search-results,.search-box").click(function (e) {
    e.stopPropagation();
  });

  $(".search-category > a").click(function (e) {
    var category = $(this).parent();
    var open = $(category).hasClass("open");
    $(category).data("state", open ? "closed" : "open");
    $(category).toggleClass("open");
    e.stopPropagation();
    return false;
  });

  $(".search-box").keyup(function () {
    var filter = $(this).val().toLowerCase();
    var results = $(this).data("results-id");

    // no search, make everything visible again
    if (filter === "") {
      $("#" + results).find(".search-category").each(function () {
        if ($(this).hasClass("date-category")) {
          $(this).addClass("hidden");
        } else {
          $(this).removeClass("hidden");
        }
        if ($(this).data("state") === "open") {
          $(this).addClass("open");
        } else {
          $(this).removeClass("open");
        }
      });
      $("#" + results).find(".searchable").removeClass("hide");
      $("#" + results).find(".no-results").addClass("hidden");
      return;
    }

    var useDate = false;
    var filterAsYear = parseInt(filter);
    if (filter.length === 4 && (1900 < filterAsYear && filterAsYear < 2100)) {
      useDate = true;
    }

    // for each category
    var total_count = 0;
    $("#" + results).find(".search-category").each(function () {
      // find all items that match
      var count = 0;
      if ($(this).hasClass("date-category") && useDate) {
        $(this).find(".searchable").each(function () {
          var value = $(this).data("search-value");
          if (value.toLowerCase().indexOf(filter) >= 0) {
            $(this).removeClass("hide");
            count += 1;
          } else {
            $(this).addClass("hide");
          }
        });
      } else if ($(this).hasClass("date-category")) {
        $(this).addClass("hidden");
        count = 0;
      } else if (!$(this).hasClass("date-category") && useDate) {
        $(this).addClass("hidden");
        count = 0;
      } else {
        $(this).find(".searchable").each(function () {
          var value = $(this).data("search-value");
          if (value.toLowerCase().indexOf(filter) >= 0) {
            $(this).removeClass("hide");
            count += 1;
          } else {
            $(this).addClass("hide");
          }
        });
      }

      // hide or not based on our count
      if (count > 0) {
        $(this).removeClass("hidden").addClass("open");
      } else {
        $(this).addClass("hidden");
      }

      total_count += count;
    });

    if (total_count === 0) {
      $("#" + results).find(".no-results").removeClass("hidden");
    } else {
      $("#" + results).find(".no-results").addClass("hidden");
    }
  });
});
