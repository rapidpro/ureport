// wires in any facebook shares on the page
$(function () {
  $(".facebook-share").on("click", function () {
    var shareURL = $(this).data("url");
    FB.ui({
      method: "share",
      href: shareURL
    });
  });
});
