// wire in our countries dropdown
$(function () {
  $(".region-dropdown > a").click(function (e) {
    var category = $(this).parent();
    var open = $(category).hasClass("open");
    $(category).data("state", open ? "closed" : "open");
    $(category).siblings().removeClass("open");
    $(category).toggleClass("open");
    e.stopPropagation();
    return false;
  });
});
