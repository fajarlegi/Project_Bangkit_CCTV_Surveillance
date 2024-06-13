$(document).ready(function() {
    $("#datepicker").datepicker({
        dateFormat: 'yy-mm-dd',
        onSelect: function(dateText) {
            filterTableByDate(dateText);
        }
    });

    function filterTableByDate(date) {
        $("table tbody tr").each(function() {
            var rowDate = $(this).find("td:nth-child(3)").text();
            if (rowDate.includes(date)) {
                $(this).show();
            } else {
                $(this).hide();
            }
        });
    }
});