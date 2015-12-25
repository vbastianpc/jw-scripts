#!/bin/bash
#
# broadcast-index
#
# Requires: GNU sed, curl/wget
#
# Index tv.jw.org by processing the files from mediator.jw.org
# and create m3u playlists, which can be played by e.g. Kodi.
#

error()
{
    echo "${@:-Something went wrong}" 1>&2
    exit 1
}

show_help()
{
    cat<<EOF
Index tv.jw.org and save the video links in m3u playlists

Usage: kodiator [options] [DIRECTORY]
  --lang LANGUAGE       Language to download. Selecting no language
                        will show a list of available language codes
  --no-recursive        Just download this file/category
  --category CATEGORY   Name of the file/category to index
  --quality QUALITY	Choose between 240, 360, 480 and 720
  DIRECTORY             Directory to save the playlists in

  
EOF
    exit
}

# Remove the history file
cleanup()
{
    # The history file needs to be keeped all the time kodiator is running
    # The CLEANUP variable is so that the subprocesses don't remove it.
    ((CLEANUP)) && [[ -e $histfile ]] && rm "$histfile"
}

# Add newline around squiggly and square brackets and replace commas with newline
# but do nothing if they are quoted
unsquash_file()
{
    sed '
	# Add a newline after all "special" characters
	# Note how the character list starts with an ]
	# Smart huh?
	s/[][{},]/\n&\n/g

' | sed -n '
	: start
	# Does this row have an uneven number of citation marks?
	# That means that the quote continues on the next line...
	/^\([^"\n]*"[^"\n]*"\)*[^"\n]*"[^"\n]*$/ {
	    # Append the next line of input
	    N
	    # Remove the newline between the two lines of input
	    s/\n//g   
	    # Go back to start again
	    b start
	}
	# If the line is fine, print it
	p
' | sed '
	# Remove all commas and empty lines
	/^,\?$/d
'
}

# Read the formated JSON file on stdin
# write videos to playlists
# and download and parse new categories
#
# GIGANT CAVEATS:
# - "key" must be followed by "name"
# - "title" must come before "progressiveDownloadURL"
#
parse_lines()
{

    # Create directory
    if [[ ! -e $savedir ]]; then
	mkdir -p "$savedir" || error "$savedir: Failed to create directory"
    fi

    # Start on an empty playlist
    if [[ ! -e $savedir/$category.m3u ]]; then
	    echo "#EXTM3U" > "$savedir/$category.m3u" || error "Failed to write to playlist"
    fi

    # Read stdin
    while read -r; do
	# Remove quotes from REPLY
	input="${REPLY//\"/}"
	case "$input" in

	    key:*)
		key="${input#*:}"
		;;

	    # A new category - parse it
	    name:*)
		name="${input#*:}"
		# Start a new instance - download and parse category
		if ((RECURSIVE)) && ! grep -q "$key" "$histfile"; then
		    [[ $key != "$category" ]] && print_to_file "# $name" "$key.m3u"
		    ("$0" --no-cleanup --category "$key")
		fi
		;;

	    # A new clip - save the old one
	    title:*)
		# If there is a title an URL, print them
		if [[ $title && $url ]]; then
		    print_to_file "# $title" "$url"
		    # Unset title and URL so they don't get repeated
		    unset title url
		fi

		# Save the new title
		title="${input#*:}"
		;;

	    # The URL we want - save it
	    progressiveDownloadURL:*${quality}P.mp4)
		url="${input#*:}"
		;;

	    # Another URL - is it better?
	    progressiveDownloadURL:*)
		if [[ $url ]]; then
		    n="$(sed 's/^.*r\([0-9]\)*P.mp4$/\1/'<<< "${input#*:}")" # new quality
		    o="$(sed 's/^.*r\([0-9]\)*P.mp4$/\1/' <<< "$url")" # old quality
		    # Save if it's better than the old one, but not bigger than maximum
		    [[ $n -gt $o && $n -lt $quality ]] && url="${input#*:}"
		fi
		;;
	esac
    done

    # If there is a title and an URL left when we reach EOF
    # save them to the playlist
    if [[ $title && $url ]]; then
	print_to_file "# $title" "$url"
    fi
}

# Print text to the playlist
print_to_file()
{
    # Write to file
    printf '%s\n' "$@" >> "$savedir/$category.m3u"
    # Remove the title and URL so they don't get repeated at EOF
    unset title url
}

# Download the language list and make it readable
# CAVEATS:
# - "name" must be followed by "code"
lang_list()
{
    # 1. Download the list
    # 2. Make newline at every opening bracket
    #    where a new language starts
    # 3. Replace "name":"LANG" ... "code":"CODE"
    #    with LANG CODE
    # 4. Sort it
    # 5. Switch place on LANG and CODE
    # 6. Make a nice list with columns
    download_file "$langurl" \
        | sed 's/{/\n/g' \
        | sed -n 's/.*"name":"\([^"]*\)".*"code":"\([^"]*\)".*/\1:\2/p' \
        | sort \
        | sed 's/\(.*\):\(.*\)/\2:\1/' \
        | column -t -s :
}

# Download a file with curl or wget
download_file()
{
    if ((CURL)); then
	curl --silent "$1" || error "Failed to download file"
    else
	wget --quiet -O - "$1" || error "Failed to download file"
    fi
}

# Check requirements
type sed &>/dev/null || error "This script requires GNU sed"

if type curl &>/dev/null; then
    CURL=1
else
    type wget &>/dev/null || error "This script requires curl or wget"
    CURL=0
fi

sed --version | egrep -q "GNU sed" || cat <<EOF
Warning:
This script is build for and tested only with GNU sed.
It looks like you are using a different version of sed,
so I canot guarrantee that it will work for you.
Just saying :)

EOF

# Arguments
while [[ $1 ]]; do
    case $1 in
        --help) show_help
            ;;
        --no-recursive) RECURSIVE=0
            ;;
        --lang)
            if [[ $2 ]]; then
		lang="$2"
	    else
		LANGLIST=1
	    fi
            ;;
	--category)
	    category="$2"
	    shift
	    ;;
	--quality)
	    quality="$2"
	    shift
	    ;;
	# see cleanup()
	--no-cleanup)
	    CLEANUP=0
	    ;;
        --*) error "Unknown flag: $1"
            ;;
        *) break
            ;;
    esac
    shift
done

# Assign variables
export lang savedir quality
savedir="${1:-./JWBroadcasting-$lang}"
[[ $CLEANUP ]] || CLEANUP=1
[[ $lang ]] || lang=E
[[ $RECURSIVE ]] || RECURSIVE=1
[[ $category ]] || category=VideoOnDemand
[[ $quality ]] || quality=480
histfile="/tmp/.broadcast-index.history"
baseurl="http://mediator.jw.org/v1/categories/$lang/${category}?detailed=1"
langurl="http://mediator.jw.org/v1/languages/E/web"

# Check if language is correct
download_file "$langurl" | grep -q "\"code\":\"$lang\"" || LANGLIST=1

# Show the language list, maybe
if ((LANGLIST)); then
    lang_list
    exit
fi

# Clean up before exit
trap 'cleanup' SIGINT SIGTERM SIGHUP EXIT

# Write to the history file
# and show a message with our progress at the same time
cleanup
echo "$category" | tee -a "$histfile"

# Download and parse the JSON file
download_file "$baseurl" | unsquash_file | parse_lines || error

# Rename the "first" file so it ends up at the top
# (use CLEANUP to see if we are parent or child process - because we're lazy)
if ((CLEANUP)); then
    mv "$storepath/$category.m3u" "$storepath/00 $category.m3u"
fi
