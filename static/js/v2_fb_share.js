// wires in any facebook shares on the page
$(function () {
  $(".facebook-share").on("click", function () {
    var shareURL = $(this).data("url");
    var url = "https://www.facebook.com/sharer/sharer.php?u=" + shareURL;
    FB.ui({
      method: "share",
      href: shareURL
    },
    function (response) {
      console.log(response);
    });
  });
});
