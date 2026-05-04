$(function () {
  $(".stories-filters input.category").change(function () {
    var catId = $(this).attr("value");
    console.log(catId);
    if (catId === "-1") {
      $("li.archived-story").show();
    } else {
      $("li.archived-story").hide();
      $("li.archived-story[data-category=" + catId + "]").show();
    }
  });
});
